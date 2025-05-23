/**
 * Основной JavaScript файл для системы автоматической генерации тестов
 */

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация всплывающих подсказок Bootstrap
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Инициализация счетчика времени для теста
    initTestTimer();
    
    // Обработчик для предварительного просмотра генерации вопросов
    initPreviewGeneration();
    
    // Валидация форм
    initFormValidation();
});

/**
 * Инициализация таймера для прохождения теста
 */
function initTestTimer() {
    const timerElement = document.getElementById('test-timer');
    if (!timerElement) return;
    
    const duration = parseInt(timerElement.dataset.duration || 30, 10);
    let timeLeft = duration * 60; // Конвертируем минуты в секунды
    
    const timerInterval = setInterval(function() {
        timeLeft--;
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            document.getElementById('test-form').submit();
            return;
        }
        
        const minutes = Math.floor(timeLeft / 60);
        const seconds = timeLeft % 60;
        
        timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        // Изменение цвета таймера при малом количестве времени
        if (timeLeft <= 60) {
            timerElement.classList.add('text-danger');
            timerElement.classList.add('fw-bold');
        } else if (timeLeft <= 300) {
            timerElement.classList.add('text-warning');
        }
    }, 1000);
}

/**
 * Инициализация предварительного просмотра генерации вопросов
 */
function initPreviewGeneration() {
    const previewButton = document.getElementById('generate-preview-btn');
    if (!previewButton) return;
    
    previewButton.addEventListener('click', function() {
        const textArea = document.getElementById('text_content');
        const previewContainer = document.getElementById('preview-container');
        const loadingSpinner = document.getElementById('preview-loading');
        
        if (!textArea || !textArea.value.trim()) {
            alert('Пожалуйста, введите текст для анализа');
            return;
        }
        
        // Показываем индикатор загрузки
        if (loadingSpinner) loadingSpinner.classList.remove('d-none');
        
        // Очищаем предыдущий предпросмотр
        if (previewContainer) previewContainer.innerHTML = '';
        
        // Отправляем запрос на сервер
        fetch('/api/generate-preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                text: textArea.value,
                num_questions: 3 // Ограничиваем количество вопросов для предпросмотра
            }),
        })
        .then(response => response.json())
        .then(data => {
            if (loadingSpinner) loadingSpinner.classList.add('d-none');
            
            if (data.error) {
                if (previewContainer) {
                    previewContainer.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                }
                return;
            }
            
            if (!data.questions || data.questions.length === 0) {
                if (previewContainer) {
                    previewContainer.innerHTML = `<div class="alert alert-warning">Не удалось сгенерировать вопросы. Попробуйте другой текст.</div>`;
                }
                return;
            }
            
            // Отображаем сгенерированные вопросы
            displayPreviewQuestions(data.questions, previewContainer);
        })
        .catch(error => {
            console.error('Error:', error);
            if (loadingSpinner) loadingSpinner.classList.add('d-none');
            if (previewContainer) {
                previewContainer.innerHTML = `<div class="alert alert-danger">Произошла ошибка при генерации вопросов</div>`;
            }
        });
    });
}

/**
 * Отображение предварительного просмотра вопросов
 */
function displayPreviewQuestions(questions, container) {
    if (!container) return;
    
    let html = '<h4 class="mt-4 mb-3">Предварительный просмотр вопросов:</h4>';
    
    questions.forEach((question, index) => {
        html += `
            <div class="question-card">
                <div class="d-flex align-items-start">
                    <span class="question-number">${index + 1}</span>
                    <div class="flex-grow-1">
                        <p class="question-text">${question.text}</p>
        `;
        
        if (question.question_type === 'multiple_choice') {
            html += '<ul class="options-list">';
            question.options.forEach(option => {
                const isCorrect = option === question.correct_answer;
                html += `
                    <li class="option-item">
                        <label class="${isCorrect ? 'text-success fw-bold' : ''}">
                            <input type="radio" disabled ${isCorrect ? 'checked' : ''}>
                            ${option} ${isCorrect ? '(правильный ответ)' : ''}
                        </label>
                    </li>
                `;
            });
            html += '</ul>';
        } else if (question.question_type === 'true_false') {
            html += '<ul class="options-list">';
            ['правда', 'ложь'].forEach(option => {
                const isCorrect = option === question.correct_answer;
                html += `
                    <li class="option-item">
                        <label class="${isCorrect ? 'text-success fw-bold' : ''}">
                            <input type="radio" disabled ${isCorrect ? 'checked' : ''}>
                            ${option} ${isCorrect ? '(правильный ответ)' : ''}
                        </label>
                    </li>
                `;
            });
            html += '</ul>';
        } else if (question.question_type === 'fill_blank') {
            html += `
                <p class="mt-2">
                    <span class="fw-bold">Правильный ответ:</span> ${question.correct_answer}
                </p>
            `;
        }
        
        html += `
                    </div>
                </div>
            </div>
        `;
    });
    
    html += `
        <div class="alert alert-info mt-3">
            <i class="fas fa-info-circle me-2"></i> Это лишь пример сгенерированных вопросов. При создании теста будет сгенерировано больше вопросов с учетом выбранных настроек.
        </div>
    `;
    
    container.innerHTML = html;
}

/**
 * Инициализация валидации форм
 */
function initFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        }, false);
    });
}

/**
 * Автосохранение ответов при прохождении теста
 */
function saveTestProgress(testId, questionId, answer) {
    // Сохраняем ответы в LocalStorage
    const storageKey = `test_${testId}_progress`;
    let progress = JSON.parse(localStorage.getItem(storageKey) || '{}');
    
    progress[questionId] = answer;
    localStorage.setItem(storageKey, JSON.stringify(progress));
}

/**
 * Загрузка сохраненного прогресса теста
 */
function loadTestProgress(testId) {
    const storageKey = `test_${testId}_progress`;
    return JSON.parse(localStorage.getItem(storageKey) || '{}');
}

/**
 * Очистка сохраненного прогресса после отправки теста
 */
function clearTestProgress(testId) {
    const storageKey = `test_${testId}_progress`;
    localStorage.removeItem(storageKey);
}

/**
 * Функция для обработки файла перед загрузкой
 */
function handleFileUpload(inputElement, previewElement) {
    if (!inputElement || !previewElement) return;
    
    inputElement.addEventListener('change', function() {
        const file = this.files[0];
        if (!file) {
            previewElement.textContent = '';
            return;
        }
        
        // Проверка типа файла
        const allowedTypes = ['text/plain', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        if (!allowedTypes.includes(file.type)) {
            alert('Пожалуйста, загрузите файл в формате .txt, .pdf или .docx');
            this.value = '';
            previewElement.textContent = '';
            return;
        }
        
        // Проверка размера файла (не более 16MB)
        if (file.size > 16 * 1024 * 1024) {
            alert('Размер файла не должен превышать 16MB');
            this.value = '';
            previewElement.textContent = '';
            return;
        }
        
        // Отображаем имя файла
        previewElement.textContent = file.name;
    });
}