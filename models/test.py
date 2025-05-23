from datetime import datetime

class Question:
    def __init__(self, question_type, text, options=None, correct_answer=None):
        self.question_type = question_type  # 'multiple_choice', 'true_false', 'fill_blank'
        self.text = text
        self.options = options or []
        self.correct_answer = correct_answer
    
    @staticmethod
    def from_dict(question_dict):
        return Question(
            question_type=question_dict.get('question_type'),
            text=question_dict.get('text'),
            options=question_dict.get('options', []),
            correct_answer=question_dict.get('correct_answer')
        )
    
    def to_dict(self):
        return {
            'question_type': self.question_type,
            'text': self.text,
            'options': self.options,
            'correct_answer': self.correct_answer
        }

class Test:
    def __init__(self, _id=None, title='', description='', creator_id=None, 
                 questions=None, category='', duration=30, is_public=False,
                 created_at=None, updated_at=None):
        self._id = _id
        self.title = title
        self.description = description
        self.creator_id = creator_id
        self.questions = questions or []
        self.category = category
        self.duration = duration  # в минутах
        self.is_public = is_public
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
    
    @staticmethod
    def from_db_document(test_doc):
        if not test_doc:
            return None
        
        questions = [Question.from_dict(q) for q in test_doc.get('questions', [])]
        
        return Test(
            _id=test_doc.get('_id'),
            title=test_doc.get('title'),
            description=test_doc.get('description'),
            creator_id=test_doc.get('creator_id'),
            questions=questions,
            category=test_doc.get('category', ''),
            duration=test_doc.get('duration', 30),
            is_public=test_doc.get('is_public', False),
            created_at=test_doc.get('created_at'),
            updated_at=test_doc.get('updated_at')
        )
    
    def to_db_document(self):
        return {
            'title': self.title,
            'description': self.description,
            'creator_id': self.creator_id,
            'questions': [q.to_dict() for q in self.questions],
            'category': self.category,
            'duration': self.duration,
            'is_public': self.is_public,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    def add_question(self, question):
        self.questions.append(question)
        self.updated_at = datetime.utcnow()
    
    def remove_question(self, index):
        if 0 <= index < len(self.questions):
            self.questions.pop(index)
            self.updated_at = datetime.utcnow()
    
    def get_question_count(self):
        return len(self.questions)