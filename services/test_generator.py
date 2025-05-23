from services.nlp_service import NLPService
from models.test import Test, Question
import random
from datetime import datetime

class TestGenerator:
    def __init__(self):
        self.nlp_service = NLPService()
    
    def generate_test_from_text(self, title, description, text, creator_id, 
                                category='', num_questions=10, duration=30, is_public=False):
        """
        Генерирует тест на основе текста с использованием NLP
        
        Args:
            title (str): Название теста
            description (str): Описание теста
            text (str): Текст для анализа и генерации вопросов
            creator_id: ID создателя теста
            category (str): Категория теста
            num_questions (int): Количество вопросов
            duration (int): Продолжительность теста в минутах
            is_public (bool): Публичность теста
            
        Returns:
            Test: Сгенерированный тест
        """
        # Генерация вопросов с помощью NLP сервиса
        question_dicts = self.nlp_service.generate_questions(text, num_questions)
        
        # Преобразование словарей вопросов в объекты Question
        questions = []
        for q_dict in question_dicts:
            question = Question(
                question_type=q_dict['question_type'],
                text=q_dict['text'],
                options=q_dict['options'],
                correct_answer=q_dict['correct_answer']
            )
            questions.append(question)
        
        # Создание теста
        test = Test(
            title=title,
            description=description,
            creator_id=creator_id,
            questions=questions,
            category=category,
            duration=duration,
            is_public=is_public,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        return test
    
    def customize_test(self, test, question_types=None, shuffle_questions=False, 
                      max_questions=None, difficulty=None):
        """
        Настраивает существующий тест
        
        Args:
            test (Test): Тест для настройки
            question_types (list): Типы вопросов для включения
            shuffle_questions (bool): Перемешать ли вопросы
            max_questions (int): Максимальное количество вопросов
            difficulty (str): Сложность ('easy', 'medium', 'hard')
            
        Returns:
            Test: Настроенный тест
        """
        questions = test.questions.copy()
        
        # Фильтрация по типам вопросов
        if question_types:
            questions = [q for q in questions if q.question_type in question_types]
        
        # Перемешивание вопросов
        if shuffle_questions:
            random.shuffle(questions)
        
        # Ограничение количества вопросов
        if max_questions and len(questions) > max_questions:
            questions = questions[:max_questions]
        
        # Настройка сложности (упрощаем или усложняем варианты ответов)
        if difficulty and questions:
            for q in questions:
                if q.question_type == 'multiple_choice':
                    if difficulty == 'easy':
                        # Для легкого уровня оставляем только 2 варианта
                        if len(q.options) > 2:
                            correct_index = q.options.index(q.correct_answer)
                            wrong_options = [opt for i, opt in enumerate(q.options) if i != correct_index]
                            q.options = [q.correct_answer, random.choice(wrong_options)]
                            random.shuffle(q.options)
                    elif difficulty == 'hard':
                        # Для сложного уровня добавляем больше вариантов, если возможно
                        if len(q.options) < 4:
                            # Генерация дополнительных вариантов
                            options_count = len(q.options)
                            additional_options = []
                            doc = self.nlp_service.nlp(q.text)
                            
                            for token in doc:
                                if token.text not in q.options and token.is_alpha and len(token.text) > 2:
                                    additional_options.append(token.text)
                                    if len(additional_options) + options_count >= 4:
                                        break
                            
                            q.options.extend(additional_options[:4-options_count])
                            random.shuffle(q.options)
        
        # Обновляем тест с новыми вопросами
        updated_test = Test(
            _id=test._id,
            title=test.title,
            description=test.description,
            creator_id=test.creator_id,
            questions=questions,
            category=test.category,
            duration=test.duration,
            is_public=test.is_public,
            created_at=test.created_at,
            updated_at=datetime.utcnow()
        )
        
        return updated_test