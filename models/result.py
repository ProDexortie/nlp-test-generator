from datetime import datetime

class TestResult:
    def __init__(self, _id=None, test_id=None, user_id=None, answers=None, 
                 score=0, max_score=0, time_spent=0, completed=False,
                 started_at=None, completed_at=None):
        self._id = _id
        self.test_id = test_id
        self.user_id = user_id
        self.answers = answers or {}  # {question_index: user_answer}
        self.score = score
        self.max_score = max_score
        self.time_spent = time_spent  # в секундах
        self.completed = completed
        self.started_at = started_at or datetime.utcnow()
        self.completed_at = completed_at
    
    @staticmethod
    def from_db_document(result_doc):
        if not result_doc:
            return None
            
        return TestResult(
            _id=result_doc.get('_id'),
            test_id=result_doc.get('test_id'),
            user_id=result_doc.get('user_id'),
            answers=result_doc.get('answers', {}),
            score=result_doc.get('score', 0),
            max_score=result_doc.get('max_score', 0),
            time_spent=result_doc.get('time_spent', 0),
            completed=result_doc.get('completed', False),
            started_at=result_doc.get('started_at'),
            completed_at=result_doc.get('completed_at')
        )
    
    def to_db_document(self):
        return {
            'test_id': self.test_id,
            'user_id': self.user_id,
            'answers': self.answers,
            'score': self.score,
            'max_score': self.max_score,
            'time_spent': self.time_spent,
            'completed': self.completed,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }
    
    def add_answer(self, question_index, answer):
        self.answers[str(question_index)] = answer
    
    def complete_test(self, score, max_score, time_spent):
        self.score = score
        self.max_score = max_score
        self.time_spent = time_spent
        self.completed = True
        self.completed_at = datetime.utcnow()
    
    def get_percentage_score(self):
        if self.max_score == 0:
            return 0
        return (self.score / self.max_score) * 100