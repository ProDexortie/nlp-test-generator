from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
import csv
import io
import os
import datetime
import json

# Импорт моделей
from models.user import User
from models.test import Test, Question
from models.result import TestResult

# Импорт сервисов
from services.nlp_service import NLPService
from services.test_generator import TestGenerator
from services.test_grader import TestGrader

# Импорт конфигурации
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Настройка папки для загрузки файлов
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация клиента MongoDB
mongo_client = MongoClient(app.config['MONGO_URI'])
db = mongo_client.get_database('nlp_test_generator')

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Инициализация сервисов
nlp_service = NLPService(app.config['SPACY_MODEL'])
test_generator = TestGenerator()
test_grader = TestGrader()

# Функция загрузки пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    user_doc = db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        return None
    return User.from_db_document(user_doc)

# Функция для проверки допустимости файла
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Маршруты приложения
@app.route('/')
def index():
    """Главная страница"""
    # Получаем публичные тесты для отображения
    public_tests = list(db.tests.find({"is_public": True}).sort("created_at", -1).limit(5))
    
    # Если пользователь авторизован, добавляем его недавние тесты
    user_recent_tests = []
    if current_user.is_authenticated:
        user_recent_tests = list(db.tests.find({"creator_id": ObjectId(current_user.get_id())}).sort("created_at", -1).limit(5))
    
    return render_template('index.html', public_tests=public_tests, user_recent_tests=user_recent_tests)

# Маршруты аутентификации
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_doc = db.users.find_one({"email": email})
        if user_doc and user_doc['password'] == password:  # Без хеширования для упрощения
            user = User.from_db_document(user_doc)
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Неверный email или пароль', 'danger')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Страница регистрации"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'student')
        
        # Проверки валидации
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return render_template('auth/register.html')
        
        # Проверка на существование пользователя с таким email
        existing_user = db.users.find_one({"email": email})
        if existing_user:
            flash('Пользователь с таким email уже существует', 'danger')
            return render_template('auth/register.html')
        
        # Создание нового пользователя
        user = User(username=username, email=email, password=password, role=role)
        user_id = db.users.insert_one(user.to_db_document()).inserted_id
        user._id = user_id
        
        login_user(user)
        flash('Регистрация успешна', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    return redirect(url_for('index'))

# Маршруты dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    """Личный кабинет пользователя"""
    # Перенаправление на соответствующую панель в зависимости от роли
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    elif current_user.is_teacher():
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

@app.route('/dashboard/admin')
@login_required
def admin_dashboard():
    """Панель администратора"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('dashboard'))
    
    # Получаем статистику пользователей
    user_count = db.users.count_documents({})
    test_count = db.tests.count_documents({})
    result_count = db.results.count_documents({})
    
    # Получаем список пользователей
    users = list(db.users.find().sort("created_at", -1))
    
    return render_template('dashboard/admin.html', user_count=user_count, 
                          test_count=test_count, result_count=result_count, users=users)

@app.route('/dashboard/teacher')
@login_required
def teacher_dashboard():
    """Панель преподавателя"""
    if not current_user.is_teacher() and not current_user.is_admin():
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('dashboard'))
    
    # Получаем тесты, созданные данным преподавателем
    tests = list(db.tests.find({"creator_id": ObjectId(current_user.get_id())}).sort("created_at", -1))
    
    # Получаем результаты тестов студентов
    test_ids = [test['_id'] for test in tests]
    results = list(db.results.find({"test_id": {"$in": test_ids}}).sort("completed_at", -1))
    
    # Получаем информацию о студентах
    student_ids = [result['user_id'] for result in results]
    students = list(db.users.find({"_id": {"$in": student_ids}, "role": "student"}))
    students_dict = {str(student['_id']): student for student in students}
    
    return render_template('dashboard/teacher.html', tests=tests, results=results, students=students_dict)

@app.route('/dashboard/student')
@login_required
def student_dashboard():
    """Панель студента"""
    # Получаем тесты, доступные для студента (публичные или назначенные)
    available_tests = list(db.tests.find({"is_public": True}).sort("created_at", -1))
    
    # Получаем результаты тестов, пройденных студентом
    user_results = list(db.results.find({"user_id": ObjectId(current_user.get_id())}).sort("completed_at", -1))
    
    # Получаем информацию о тестах, которые прошел студент
    completed_test_ids = [result['test_id'] for result in user_results]
    completed_tests = list(db.tests.find({"_id": {"$in": completed_test_ids}}))
    tests_dict = {str(test['_id']): test for test in completed_tests}
    
    return render_template('dashboard/student.html', available_tests=available_tests, 
                          user_results=user_results, tests=tests_dict)

# Маршруты управления тестами
@app.route('/test/create', methods=['GET', 'POST'])
@login_required
def create_test():
    """Создание нового теста"""
    if not current_user.is_teacher() and not current_user.is_admin():
        flash('Только преподаватели могут создавать тесты', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        duration = int(request.form.get('duration', 30))
        num_questions = int(request.form.get('num_questions', 10))
        is_public = request.form.get('is_public') == 'on'
        
        # Получение текста для анализа
        text_content = request.form.get('text_content')
        
        # Если был загружен файл
        if 'text_file' in request.files:
            file = request.files['text_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Чтение содержимого файла
                with open(filepath, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                
                # Удаление временного файла
                os.remove(filepath)
        
        if not text_content:
            flash('Необходимо ввести текст или загрузить файл', 'danger')
            return render_template('test/create.html')
        
        # Генерация теста
        try:
            test = test_generator.generate_test_from_text(
                title=title,
                description=description,
                text=text_content,
                creator_id=ObjectId(current_user.get_id()),
                category=category,
                num_questions=num_questions,
                duration=duration,
                is_public=is_public
            )
            
            # Сохранение теста в БД
            test_id = db.tests.insert_one(test.to_db_document()).inserted_id
            
            flash('Тест успешно создан', 'success')
            return redirect(url_for('view_test', test_id=test_id))
        except Exception as e:
            flash(f'Ошибка при создании теста: {str(e)}', 'danger')
    
    return render_template('test/create.html')

@app.route('/test/<test_id>')
def view_test(test_id):
    """Просмотр информации о тесте"""
    test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    test = Test.from_db_document(test_doc)
    
    # Проверка прав доступа
    is_owner = current_user.is_authenticated and str(test.creator_id) == current_user.get_id()
    is_public = test.is_public
    is_admin = current_user.is_authenticated and current_user.is_admin()
    
    if not (is_owner or is_public or is_admin):
        flash('У вас нет доступа к этому тесту', 'danger')
        return redirect(url_for('dashboard'))
    
    # Получаем информацию о создателе теста
    creator = None
    if test.creator_id:
        creator_doc = db.users.find_one({"_id": test.creator_id})
        if creator_doc:
            creator = User.from_db_document(creator_doc)
    
    return render_template('test/view.html', test=test, creator=creator, is_owner=is_owner)

@app.route('/test/<test_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_test(test_id):
    """Редактирование теста"""
    test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    test = Test.from_db_document(test_doc)
    
    # Проверка прав доступа
    is_owner = str(test.creator_id) == current_user.get_id()
    is_admin = current_user.is_admin()
    
    if not (is_owner or is_admin):
        flash('У вас нет прав на редактирование этого теста', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        duration = int(request.form.get('duration', 30))
        is_public = request.form.get('is_public') == 'on'
        
        # Обновляем базовую информацию о тесте
        test.title = title
        test.description = description
        test.category = category
        test.duration = duration
        test.is_public = is_public
        test.updated_at = datetime.datetime.utcnow()
        
        # Обновляем вопросы, если есть изменения
        for i, question in enumerate(test.questions):
            question_key = f'question_{i}'
            if question_key in request.form:
                question.text = request.form.get(f'question_{i}')
                
                # Обновление вариантов ответа для вопросов с множественным выбором
                if question.question_type == 'multiple_choice':
                    options = []
                    for j in range(4):  # максимум 4 варианта
                        option_key = f'option_{i}_{j}'
                        if option_key in request.form and request.form.get(option_key).strip():
                            options.append(request.form.get(option_key))
                    
                    if options:
                        question.options = options
                
                # Обновление правильного ответа
                correct_answer_key = f'correct_answer_{i}'
                if correct_answer_key in request.form:
                    question.correct_answer = request.form.get(correct_answer_key)
        
        # Сохраняем изменения в БД
        db.tests.update_one(
            {"_id": ObjectId(test_id)},
            {"$set": test.to_db_document()}
        )
        
        flash('Тест успешно обновлен', 'success')
        return redirect(url_for('view_test', test_id=test_id))
    
    return render_template('test/edit.html', test=test)

@app.route('/test/<test_id>/delete', methods=['POST'])
@login_required
def delete_test(test_id):
    """Удаление теста"""
    test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    # Проверка прав доступа
    is_owner = str(test_doc['creator_id']) == current_user.get_id()
    is_admin = current_user.is_admin()
    
    if not (is_owner or is_admin):
        flash('У вас нет прав на удаление этого теста', 'danger')
        return redirect(url_for('dashboard'))
    
    # Удаление теста и связанных результатов
    db.tests.delete_one({"_id": ObjectId(test_id)})
    db.results.delete_many({"test_id": ObjectId(test_id)})
    
    flash('Тест успешно удален', 'success')
    return redirect(url_for('dashboard'))

# Маршруты для прохождения тестов
@app.route('/test/<test_id>/take')
@login_required
def take_test(test_id):
    """Страница прохождения теста"""
    test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    test = Test.from_db_document(test_doc)
    
    # Проверка доступности теста
    if not test.is_public and str(test.creator_id) != current_user.get_id() and not current_user.is_admin():
        flash('У вас нет доступа к этому тесту', 'danger')
        return redirect(url_for('dashboard'))
    
    # Проверяем, не проходил ли пользователь уже этот тест
    existing_result = db.results.find_one({
        "test_id": ObjectId(test_id),
        "user_id": ObjectId(current_user.get_id()),
        "completed": True
    })
    
    if existing_result:
        flash('Вы уже проходили этот тест', 'info')
        return redirect(url_for('view_result', result_id=existing_result['_id']))
    
    # Создаем новую запись о начале прохождения теста
    result = TestResult(
        test_id=ObjectId(test_id),
        user_id=ObjectId(current_user.get_id()),
        started_at=datetime.datetime.utcnow()
    )
    
    result_id = db.results.insert_one(result.to_db_document()).inserted_id
    
    # Сохраняем ID результата в сессии для отслеживания времени
    session['current_test_start'] = datetime.datetime.utcnow().timestamp()
    session['current_test_id'] = str(test_id)
    session['current_result_id'] = str(result_id)
    
    return render_template('test/take.html', test=test, result_id=result_id)

@app.route('/test/<test_id>/submit', methods=['POST'])
@login_required
def submit_test(test_id):
    """Отправка ответов на тест"""
    if 'current_test_id' not in session or session['current_test_id'] != test_id:
        flash('Ошибка при отправке теста', 'danger')
        return redirect(url_for('dashboard'))
    
    test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    test = Test.from_db_document(test_doc)
    result_id = session['current_result_id']
    
    # Рассчитываем затраченное время
    start_time = session.get('current_test_start', 0)
    time_spent = int(datetime.datetime.utcnow().timestamp() - start_time)
    
    # Собираем ответы пользователя
    answers = {}
    for i in range(len(test.questions)):
        answer_key = f'answer_{i}'
        if answer_key in request.form:
            answers[str(i)] = request.form.get(answer_key)
    
    # Оцениваем тест
    grading_result = test_grader.grade_test(test, answers, time_spent)
    
    # Обновляем результат в БД
    db.results.update_one(
        {"_id": ObjectId(result_id)},
        {"$set": {
            "answers": answers,
            "score": grading_result['score'],
            "max_score": grading_result['max_score'],
            "time_spent": time_spent,
            "completed": True,
            "completed_at": datetime.datetime.utcnow()
        }}
    )
    
    # Очищаем сессию
    session.pop('current_test_start', None)
    session.pop('current_test_id', None)
    session.pop('current_result_id', None)
    
    flash('Тест успешно завершен', 'success')
    return redirect(url_for('view_result', result_id=result_id))

@app.route('/result/<result_id>')
@login_required
def view_result(result_id):
    """Просмотр результатов теста"""
    result_doc = db.results.find_one({"_id": ObjectId(result_id)})
    if not result_doc:
        flash('Результат не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    result = TestResult.from_db_document(result_doc)
    
    # Проверка прав доступа
    is_owner = str(result.user_id) == current_user.get_id()
    is_teacher = current_user.is_teacher() or current_user.is_admin()
    
    if not (is_owner or is_teacher):
        flash('У вас нет доступа к этим результатам', 'danger')
        return redirect(url_for('dashboard'))
    
    # Получаем информацию о тесте
    test_doc = db.tests.find_one({"_id": result.test_id})
    if not test_doc:
        flash('Тест не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    test = Test.from_db_document(test_doc)
    
    # Создаем детальные результаты для отображения
    question_results = []
    for i, question in enumerate(test.questions):
        answer = result.answers.get(str(i), "")
        is_correct = False
        
        if question.question_type == 'multiple_choice':
            is_correct = answer == question.correct_answer
        elif question.question_type == 'true_false':
            is_correct = answer == question.correct_answer
        elif question.question_type == 'fill_blank':
            is_correct = answer.lower().strip() == question.correct_answer.lower().strip()
        
        question_results.append({
            'question': question,
            'user_answer': answer,
            'is_correct': is_correct
        })
    
    # Получаем информацию о пользователе
    user_doc = db.users.find_one({"_id": result.user_id})
    user = User.from_db_document(user_doc) if user_doc else None
    
    return render_template('test/results.html', result=result, test=test, 
                          question_results=question_results, user=user)

# API маршруты для AJAX запросов
@app.route('/api/generate-preview', methods=['POST'])
@login_required
def api_generate_preview():
    """API для предварительной генерации вопросов"""
    if not current_user.is_teacher() and not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    data = request.get_json()
    text = data.get('text', '')
    num_questions = int(data.get('num_questions', 3))
    
    if not text:
        return jsonify({"error": "Текст не предоставлен"}), 400
    
    try:
        # Генерируем небольшой набор вопросов для предпросмотра
        preview_questions = nlp_service.generate_questions(text, num_questions)
        return jsonify({"questions": preview_questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API маршруты для администратора
@app.route('/api/admin/tests', methods=['GET'])
@login_required
def api_admin_get_tests():
    """API для получения списка всех тестов"""
    if not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        # Получаем все тесты
        tests_cursor = db.tests.find().sort("created_at", -1)
        tests = []
        
        # Получаем информацию о создателях
        user_ids = []
        for test_doc in tests_cursor:
            if test_doc.get('creator_id'):
                user_ids.append(test_doc['creator_id'])
        
        # Получаем данные пользователей-создателей
        users_cursor = db.users.find({"_id": {"$in": user_ids}})
        users_dict = {str(user['_id']): user for user in users_cursor}
        
        # Снова получаем тесты (курсор уже исчерпан)
        tests_cursor = db.tests.find().sort("created_at", -1)
        
        for test_doc in tests_cursor:
            creator_id = str(test_doc.get('creator_id', ''))
            creator = users_dict.get(creator_id, {})
            
            test_data = {
                '_id': str(test_doc['_id']),
                'title': test_doc.get('title', ''),
                'category': test_doc.get('category', ''),
                'creator_name': creator.get('username', 'Неизвестно'),
                'question_count': len(test_doc.get('questions', [])),
                'is_public': test_doc.get('is_public', False),
                'created_at': test_doc.get('created_at', datetime.datetime.utcnow()).isoformat()
            }
            tests.append(test_data)
        
        return jsonify({"tests": tests})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/tests/<test_id>', methods=['DELETE'])
@login_required
def api_admin_delete_test(test_id):
    """API для удаления теста"""
    if not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        # Проверяем существование теста
        test_doc = db.tests.find_one({"_id": ObjectId(test_id)})
        if not test_doc:
            return jsonify({"error": "Тест не найден"}), 404
        
        # Удаляем тест и связанные результаты
        db.tests.delete_one({"_id": ObjectId(test_id)})
        db.results.delete_many({"test_id": ObjectId(test_id)})
        
        return jsonify({"message": "Тест успешно удален"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users', methods=['POST'])
@login_required
def api_admin_create_user():
    """API для создания пользователя"""
    if not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        data = request.get_json()
        
        # Валидация данных
        required_fields = ['username', 'email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Поле {field} обязательно"}), 400
        
        # Проверка на существование пользователя с таким email
        existing_user = db.users.find_one({"email": data['email']})
        if existing_user:
            return jsonify({"error": "Пользователь с таким email уже существует"}), 400
        
        # Создание нового пользователя
        user = User(
            username=data['username'],
            email=data['email'],
            password=data['password'],  # В реальном проекте нужно хешировать
            role=data['role']
        )
        
        user_id = db.users.insert_one(user.to_db_document()).inserted_id
        
        return jsonify({
            "message": "Пользователь успешно создан",
            "user_id": str(user_id)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['PUT'])
@login_required
def api_admin_update_user(user_id):
    """API для обновления пользователя"""
    if not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        data = request.get_json()
        
        # Проверяем существование пользователя
        user_doc = db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        # Подготавливаем данные для обновления
        update_data = {}
        
        if 'username' in data:
            update_data['username'] = data['username']
        
        if 'email' in data:
            # Проверяем, не занят ли email другим пользователем
            existing_user = db.users.find_one({
                "email": data['email'],
                "_id": {"$ne": ObjectId(user_id)}
            })
            if existing_user:
                return jsonify({"error": "Пользователь с таким email уже существует"}), 400
            update_data['email'] = data['email']
        
        if 'role' in data:
            update_data['role'] = data['role']
        
        if 'password' in data and data['password']:
            update_data['password'] = data['password']  # В реальном проекте нужно хешировать
        
        if update_data:
            db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
        
        return jsonify({"message": "Пользователь успешно обновлен"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@login_required
def api_admin_delete_user(user_id):
    """API для удаления пользователя"""
    if not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        # Проверяем существование пользователя
        user_doc = db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        # Запрещаем удаление самого себя
        if str(user_doc['_id']) == current_user.get_id():
            return jsonify({"error": "Нельзя удалить самого себя"}), 400
        
        # Удаляем пользователя и связанные данные
        db.users.delete_one({"_id": ObjectId(user_id)})
        
        # Удаляем тесты, созданные пользователем
        user_tests = db.tests.find({"creator_id": ObjectId(user_id)})
        test_ids = [test['_id'] for test in user_tests]
        
        if test_ids:
            db.tests.delete_many({"creator_id": ObjectId(user_id)})
            db.results.delete_many({"test_id": {"$in": test_ids}})
        
        # Удаляем результаты пользователя
        db.results.delete_many({"user_id": ObjectId(user_id)})
        
        return jsonify({"message": "Пользователь успешно удален"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/teacher/export-results', methods=['GET'])
@login_required
def api_teacher_export_results():
    """API для экспорта результатов тестов преподавателя в CSV"""
    if not current_user.is_teacher() and not current_user.is_admin():
        return jsonify({"error": "Доступ запрещен"}), 403
    
    try:
        # Получаем тесты, созданные данным преподавателем
        tests = list(db.tests.find({"creator_id": ObjectId(current_user.get_id())}).sort("created_at", -1))
        
        if not tests:
            return jsonify({"error": "У вас нет созданных тестов"}), 404
        
        # Получаем результаты тестов студентов
        test_ids = [test['_id'] for test in tests]
        results = list(db.results.find({"test_id": {"$in": test_ids}, "completed": True}).sort("completed_at", -1))
        
        if not results:
            return jsonify({"error": "Нет результатов для экспорта"}), 404
        
        # Получаем информацию о студентах
        student_ids = [result['user_id'] for result in results]
        students = list(db.users.find({"_id": {"$in": student_ids}}))
        students_dict = {str(student['_id']): student for student in students}
        
        # Создаем словарь тестов для быстрого доступа
        tests_dict = {str(test['_id']): test for test in tests}
        
        # Создаем CSV данные
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
        
        # Заголовки CSV
        headers = [
            'Дата прохождения',
            'Студент',
            'Email студента',
            'Название теста',
            'Категория теста',
            'Количество вопросов',
            'Правильных ответов',
            'Процент правильных',
            'Оценка (1-5)',
            'Время прохождения (мин:сек)',
            'Длительность теста (мин)'
        ]
        writer.writerow(headers)
        
        # Данные результатов
        for result in results:
            student = students_dict.get(str(result['user_id']), {})
            test = tests_dict.get(str(result['test_id']), {})
            
            # Рассчитываем процент и оценку
            percentage = (result['score'] / result['max_score'] * 100) if result['max_score'] > 0 else 0
            
            # Оценка по 5-балльной шкале
            if percentage >= 90:
                grade = 5
            elif percentage >= 75:
                grade = 4
            elif percentage >= 60:
                grade = 3
            else:
                grade = 2
            
            # Время прохождения
            time_spent = result.get('time_spent', 0)
            minutes = time_spent // 60
            seconds = time_spent % 60
            time_str = f"{minutes}:{seconds:02d}"
            
            # Дата прохождения
            completed_at = result.get('completed_at', datetime.datetime.utcnow())
            date_str = completed_at.strftime('%d.%m.%Y %H:%M') if completed_at else 'Н/Д'
            
            row = [
                date_str,
                student.get('username', 'Неизвестный'),
                student.get('email', 'Н/Д'),
                test.get('title', 'Неизвестный тест'),
                test.get('category', 'Общая'),
                result['max_score'],
                result['score'],
                f"{percentage:.1f}%",
                grade,
                time_str,
                test.get('duration', 'Н/Д')
            ]
            writer.writerow(row)
        
        # Создаем ответ с файлом
        output.seek(0)
        csv_data = output.getvalue()
        output.close()
        
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=test_results.csv'
        
        # Добавляем BOM для корректного отображения кириллицы в Excel
        csv_data_with_bom = '\ufeff' + csv_data
        response.data = csv_data_with_bom.encode('utf-8')
        
        return response
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)