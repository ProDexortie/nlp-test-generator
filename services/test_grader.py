from models.test import Test
from models.result import TestResult
import re
from datetime import datetime

class TestGrader:
    def __init__(self):
        pass
    
    def grade_test(self, test, answers, time_spent):
        """
        Оценивает выполнение теста
        
        Args:
            test (Test): Тест, который оценивается
            answers (dict): Ответы пользователя {question_index: answer}
            time_spent (int): Затраченное время в секундах
            
        Returns:
            dict: Результаты проверки
        """
        score = 0
        max_score = len(test.questions)
        question_results = []
        
        for i, question in enumerate(test.questions):
            question_index = str(i)
            user_answer = answers.get(question_index, "")
            correct = False
            
            # Проверка ответа в зависимости от типа вопроса
            if question.question_type == 'multiple_choice':
                correct = user_answer == question.correct_answer
            
            elif question.question_type == 'true_false':
                correct = user_answer == question.correct_answer
            
            elif question.question_type == 'fill_blank':
                # Для заполнения пропусков, нормализуем ответ для более гибкого сравнения
                user_answer_norm = self._normalize_text(user_answer)
                correct_answer_norm = self._normalize_text(question.correct_answer)
                correct = user_answer_norm == correct_answer_norm
            
            # Добавляем результат для этого вопроса
            question_results.append({
                'question_index': i,
                'question_text': question.text,
                'question_type': question.question_type,
                'correct_answer': question.correct_answer,
                'user_answer': user_answer,
                'is_correct': correct
            })
            
            # Если ответ правильный, начисляем баллы
            if correct:
                score += 1
        
        # Вычисляем процентную оценку
        percentage = (score / max_score) * 100 if max_score > 0 else 0
        
        # Определяем оценку по 5-балльной шкале
        grade = self._calculate_grade(percentage)
        
        result = {
            'score': score,
            'max_score': max_score,
            'percentage': percentage,
            'grade': grade,
            'time_spent': time_spent,
            'question_results': question_results
        }
        
        return result
    
    def create_test_result(self, test_id, user_id, answers, time_spent, grading_result):
        """
        Создает объект результата теста для сохранения в БД
        
        Args:
            test_id: ID теста
            user_id: ID пользователя
            answers (dict): Ответы пользователя
            time_spent (int): Затраченное время
            grading_result (dict): Результаты проверки
            
        Returns:
            TestResult: Объект результата теста
        """
        result = TestResult(
            test_id=test_id,
            user_id=user_id,
            answers=answers,
            score=grading_result['score'],
            max_score=grading_result['max_score'],
            time_spent=time_spent,
            completed=True,
            started_at=datetime.utcnow() - datetime.timedelta(seconds=time_spent),
            completed_at=datetime.utcnow()
        )
        
        return result
    
    def _normalize_text(self, text):
        """
        Нормализация текста для более гибкого сравнения ответов
        """
        if not text:
            return ""
        
        # Приведение к нижнему регистру
        normalized = text.lower()
        
        # Удаление пунктуации
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Удаление лишних пробелов
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _calculate_grade(self, percentage):
        """
        Рассчитывает оценку по 5-балльной шкале на основе процентной оценки
        """
        if percentage >= 90:
            return 5  # Отлично
        elif percentage >= 75:
            return 4  # Хорошо
        elif percentage >= 60:
            return 3  # Удовлетворительно
        else:
            return 2  # Неудовлетворительно