import spacy
import nltk
from nltk.tokenize import sent_tokenize
import random
import re
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка необходимых ресурсов NLTK
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

class NLPService:
    def __init__(self, spacy_model="ru_core_news_md"):
        # Загрузка модели spaCy
        try:
            self.nlp = spacy.load(spacy_model)
            logger.info(f"Успешно загружена модель spaCy: {spacy_model}")
        except OSError:
            # Если модель не установлена, загружаем ее
            logger.warning(f"Модель {spacy_model} не найдена. Загрузка...")
            spacy.cli.download(spacy_model)
            self.nlp = spacy.load(spacy_model)
            logger.info(f"Успешно загружена модель spaCy: {spacy_model}")
        
        # Пытаемся загрузить модели трансформеров, если не получится - используем запасной вариант
        self.use_transformers = True
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
            
            logger.info("Пытаемся загрузить модели трансформеров...")
            self.tokenizer = AutoTokenizer.from_pretrained("ceshine/t5-paraphrase-paws-msrp-opinosis")
            self.model = AutoModelForSeq2SeqLM.from_pretrained("ceshine/t5-paraphrase-paws-msrp-opinosis")
            
            # Инициализация пайплайнов
            self.summarizer = pipeline("summarization", model="IlyaGusev/mbart_ru_sum_gazeta", max_length=100)
            self.qa_pipeline = pipeline("text2text-generation", model=self.model, tokenizer=self.tokenizer)
            logger.info("Модели трансформеров успешно загружены")
            
        except (ImportError, ValueError, OSError) as e:
            self.use_transformers = False
            logger.warning(f"Не удалось загрузить модели трансформеров: {str(e)}")
            logger.info("Переключение на базовый режим без использования трансформеров")
    
    def preprocess_text(self, text):
        """Предварительная обработка текста"""
        # Удаление лишних пробелов и переносов строк
        text = re.sub(r'\s+', ' ', text)
        # Разбиение на предложения
        sentences = sent_tokenize(text)
        # Обработка с помощью spaCy для получения лемм, частей речи и т.д.
        docs = list(self.nlp.pipe(sentences))
        return docs
    
    def extract_key_sentences(self, docs, n=10):
        """Извлечение ключевых предложений для генерации вопросов"""
        # Фильтрация предложений (минимальная длина, содержит существительные)
        filtered_docs = [doc for doc in docs if len(doc) > 5 and any(token.pos_ == "NOUN" for token in doc)]
        
        # Если после фильтрации осталось мало предложений, используем оригинальные
        if len(filtered_docs) < n:
            # Сортировка по длине, чтобы выбрать наиболее информативные
            sorted_docs = sorted(docs, key=lambda x: len(x), reverse=True)
            return sorted_docs[:n]
        
        # Выбор случайных предложений из отфильтрованных
        return random.sample(filtered_docs, min(n, len(filtered_docs)))
    
    def generate_factual_question(self, sentence):
        """Генерация фактологического вопроса на основе предложения"""
        doc = self.nlp(sentence.text)
        
        # Находим именованные сущности и их типы
        entities = [(ent.text, ent.label_) for ent in doc.ents]
        
        # Находим подлежащее и сказуемое
        subject = None
        verb = None
        obj = None
        for token in doc:
            if token.dep_ in ("nsubj", "nsubjpass"):
                subject = token
                for child in token.children:
                    if child.dep_ in ("amod", "compound"):
                        subject = doc[min(child.i, token.i):max(child.i, token.i) + 1]
            if token.pos_ == "VERB" and not verb:
                verb = token
            if token.dep_ in ("dobj", "pobj", "attr") and not obj:
                obj = token
                for child in token.children:
                    if child.dep_ in ("amod", "compound"):
                        obj = doc[min(child.i, token.i):max(child.i, token.i) + 1]
        
        # Если не нашли основные компоненты, вернемся к базовому алгоритму
        if not (subject and verb):
            return self.generate_multiple_choice_question(sentence)
        
        question_text = None
        correct_answer = None
        
        # Преобразуем объекты в текст для работы
        subject_text = subject.text if hasattr(subject, 'text') else ' '.join([t.text for t in subject])
        
        # Пробуем создать вопрос о субъекте
        for token in doc:
            # Ищем информацию о принадлежности к классу/группе
            for class_word in ["раса", "тип", "класс", "категория", "вид", "род"]:
                if class_word in token.text.lower():
                    # Ищем определение класса
                    for other_token in doc:
                        if other_token.head == token and other_token.dep_ in ("amod", "nmod", "compound") and len(other_token.text) > 2:
                            question_text = f"К какой {token.text.lower()} относится {subject_text}?"
                            correct_answer = other_token.text
                            break
            
            # Ищем роли и профессии
            role_words = ["королева", "король", "президент", "генерал", "директор", "глава", "лидер", "основатель", "создатель"]
            if token.lemma_.lower() in role_words and token.dep_ in ("appos", "attr"):
                # Проверяем, что это относится к нашему субъекту
                if token.head == subject or (hasattr(subject, 'root') and token.head == subject.root):
                    question_text = f"{token.text.capitalize()} чего/кого {subject_text}?"
                    
                    # Ищем дополнение к роли
                    for child in token.children:
                        if child.dep_ in ("nmod", "dobj", "pobj"):
                            correct_answer = child.text
                            break
        
        # Проверяем, нашли ли мы вопрос
        if not question_text or not correct_answer:
            # Ищем простые отношения подлежащее-определение
            for token in doc:
                if token.head == subject and token.dep_ == "amod" and len(token.text) > 2:
                    question_text = f"Каким является {subject_text}?"
                    correct_answer = token.text
                    break
        
        # Проверяем, нашли ли мы вопрос, если нет - создаем простой вопрос о субъекте
        if not question_text or not correct_answer:
            # Если есть объект, создаем вопрос о нем
            if obj:
                obj_text = obj.text if hasattr(obj, 'text') else ' '.join([t.text for t in obj])
                question_text = f"Кто/что является {obj_text}?"
                correct_answer = subject_text
        
        # Если все методы не сработали, используем стандартный алгоритм
        if not question_text or not correct_answer:
            return self.generate_multiple_choice_question(sentence)
        
        # Генерируем дистракторы
        distractors = []
        
        # Поиск похожих слов для дистракторов в этом же документе
        for sent in doc.doc.sents:
            for token in sent:
                if token.text != correct_answer and len(token.text) > 2:
                    # Проверяем, что это подходящий дистрактор
                    if token.pos_ in ["NOUN", "PROPN", "ADJ"] and token.text not in distractors:
                        distractors.append(token.text)
        
        # Если недостаточно дистракторов, добавляем общие варианты
        if len(distractors) < 3:
            placeholder_distractors = ["другое", "нет правильного ответа", "неизвестно"]
            for distractor in placeholder_distractors:
                if distractor not in distractors:
                    distractors.append(distractor)
                if len(distractors) >= 3:
                    break
        
        # Выбираем 3 случайных дистрактора
        if len(distractors) > 3:
            distractors = random.sample(distractors, 3)
        
        # Создаем финальный список вариантов ответа
        options = distractors + [correct_answer]
        random.shuffle(options)
        
        return {
            "question_type": "multiple_choice",
            "text": question_text,
            "options": options,
            "correct_answer": correct_answer
        }
    
    def generate_multiple_choice_question(self, sentence):
        """Генерация вопроса с множественным выбором"""
        # Анализ предложения
        doc = self.nlp(sentence.text)
        
        # Находим ключевые существительные
        key_nouns = [token for token in doc if token.pos_ == "NOUN" and not token.is_stop]
        if not key_nouns:
            # Если нет существительных, ищем другие значимые слова
            key_words = [token for token in doc if token.pos_ in ["ADJ", "VERB"] and not token.is_stop]
            if not key_words:
                return None
            target_word = random.choice(key_words)
        else:
            target_word = random.choice(key_nouns)
        
        # Создаем вопрос
        question_text = sentence.text.replace(target_word.text, "_____")
        
        # Формируем варианты ответов (правильный + дистракторы)
        correct_answer = target_word.text
        
        # Находим дистракторы - слова той же части речи
        distractors = []
        for other_sent in doc.doc.sents:
            if other_sent.text != sentence.text:
                for token in other_sent:
                    if token.pos_ == target_word.pos_ and token.text != target_word.text and len(token.text) > 2:
                        distractors.append(token.text)
        
        # Собираем все слова той же части речи из текущего документа
        document_words = []
        for token in doc:
            if token.pos_ == target_word.pos_ and token.text != target_word.text and len(token.text) > 2:
                document_words.append(token.text)
        
        # Если недостаточно дистракторов из других предложений, добавляем слова из текущего документа
        for word in document_words:
            if word not in distractors and len(distractors) < 3:
                distractors.append(word)
        
        # Если все еще недостаточно, добавляем искусственные варианты
        if len(distractors) < 3:
            additional_options = [
                f"не {correct_answer}", 
                f"{correct_answer}а" if not correct_answer.endswith('а') else f"{correct_answer[:-1]}о", 
                f"{correct_answer}ы" if not correct_answer.endswith('ы') else f"{correct_answer[:-1]}и"
            ]
            for option in additional_options:
                if option not in distractors and option != correct_answer:
                    distractors.append(option)
        
        # Выбираем до 3 дистракторов
        if len(distractors) > 3:
            options = random.sample(distractors, 3)
        else:
            options = distractors[:3]
        
        # Если дистракторов все равно мало, добавляем стандартные варианты
        while len(options) < 3:
            standard_options = ["другое", "нет правильного ответа", "неизвестно"]
            for opt in standard_options:
                if opt not in options and len(options) < 3:
                    options.append(opt)
        
        # Добавляем правильный ответ и перемешиваем
        options.append(correct_answer)
        random.shuffle(options)
        
        return {
            "question_type": "multiple_choice",
            "text": question_text,
            "options": options,
            "correct_answer": correct_answer
        }
    
    def generate_true_false_question(self, sentence):
        """Генерация вопроса типа правда/ложь"""
        original_text = sentence.text
        
        # Генерация искаженного варианта предложения
        doc = self.nlp(original_text)
        
        # Выбираем, будет ли вопрос с правильным или неправильным утверждением
        is_true = random.choice([True, False])
        
        if is_true:
            # Если true, используем оригинальное предложение
            statement = original_text
            correct_answer = "правда"
        else:
            # Если false, изменяем предложение
            # Находим ключевое слово для замены
            key_tokens = [token for token in doc if token.pos_ in ["NOUN", "ADJ", "VERB", "NUM"] and not token.is_stop]
            
            if not key_tokens:
                # Если нет подходящих слов, используем отрицание
                if any(token.pos_ == "VERB" for token in doc):
                    # Находим глагол
                    verb = next(token for token in doc if token.pos_ == "VERB")
                    # Добавляем отрицание
                    statement = original_text.replace(verb.text, f"не {verb.text}")
                else:
                    # Если нет глагола, добавляем отрицание в начало
                    statement = f"Неверно, что {original_text.lower()}"
            else:
                # Выбираем случайное слово для замены
                token_to_replace = random.choice(key_tokens)
                
                # Находим подходящие слова для замены среди других токенов документа
                replacements = []
                for other_token in doc:
                    if (other_token.pos_ == token_to_replace.pos_ and 
                        other_token.text != token_to_replace.text and len(other_token.text) > 2):
                        replacements.append(other_token.text)
                
                if replacements:
                    replacement = random.choice(replacements)
                    statement = original_text.replace(token_to_replace.text, replacement)
                else:
                    # Если не нашли хороших замен, создаем противоположное слово
                    if token_to_replace.pos_ == "ADJ":
                        # Для прилагательных добавляем "не"
                        statement = original_text.replace(token_to_replace.text, f"не {token_to_replace.text}")
                    elif token_to_replace.pos_ == "VERB":
                        # Для глаголов добавляем "не"
                        statement = original_text.replace(token_to_replace.text, f"не {token_to_replace.text}")
                    elif token_to_replace.pos_ == "NOUN":
                        # Для существительных меняем на другое существительное
                        common_nouns = ["стол", "человек", "книга", "дом", "машина", "дерево", "город"]
                        replacement = random.choice(common_nouns)
                        statement = original_text.replace(token_to_replace.text, replacement)
                    else:
                        # Для всего остального используем отрицание предложения
                        statement = f"Неверно, что {original_text.lower()}"
            
            correct_answer = "ложь"
        
        return {
            "question_type": "true_false",
            "text": f"Верно ли следующее утверждение: \"{statement}\"",
            "options": ["правда", "ложь"],
            "correct_answer": correct_answer
        }
    
    def generate_fill_blank_question(self, sentence):
        """Генерация вопроса с заполнением пропуска"""
        text = sentence.text
        doc = self.nlp(text)
        
        # Находим ключевые слова (существительные, глаголы, прилагательные)
        key_tokens = [token for token in doc if token.pos_ in ["NOUN", "VERB", "ADJ"] 
                      and not token.is_stop and len(token.text) > 3]
        
        if not key_tokens:
            return None
        
        # Выбираем случайное ключевое слово
        token_to_blank = random.choice(key_tokens)
        
        # Создаем текст с пропуском
        question_text = text.replace(token_to_blank.text, "___________")
        
        return {
            "question_type": "fill_blank",
            "text": question_text,
            "options": [],
            "correct_answer": token_to_blank.text
        }
    
    def generate_questions(self, text, num_questions=10):
        """Генерация вопросов разных типов на основе текста"""
        logger.info(f"Начало генерации {num_questions} вопросов")
        
        # Предобработка текста
        docs = self.preprocess_text(text)
        
        # Если текст слишком короткий
        if len(docs) < 3:
            logger.warning("Текст слишком короткий для генерации вопросов")
            return []
        
        # Извлечение ключевых предложений
        key_sentences = self.extract_key_sentences(docs, n=min(num_questions * 2, len(docs)))
        
        questions = []
        
        try:
            # Распределение типов вопросов
            question_types = {
                'factual': int(num_questions * 0.4),       # 40% фактических вопросов
                'multiple_choice': int(num_questions * 0.3),  # 30% вопросов с множественным выбором
                'true_false': int(num_questions * 0.2),      # 20% вопросов правда/ложь
                'fill_blank': num_questions - int(num_questions * 0.4) - int(num_questions * 0.3) - int(num_questions * 0.2)  # 10% с заполнением пропусков
            }
            
            logger.info(f"Распределение типов вопросов: {question_types}")
            
            # Перемешиваем предложения
            random.shuffle(key_sentences)
            
            # Генерация фактических вопросов
            try:
                for i in range(min(question_types['factual'], len(key_sentences))):
                    try:
                        question = self.generate_factual_question(key_sentences[i])
                        if question:
                            questions.append(question)
                    except Exception as e:
                        logger.error(f"Ошибка при генерации фактического вопроса: {str(e)}")
                        continue
            except Exception as e:
                logger.error(f"Ошибка в блоке генерации фактических вопросов: {str(e)}")
            
            # Генерация вопросов с множественным выбором
            try:
                for i in range(min(question_types['multiple_choice'], len(key_sentences) - len(questions))):
                    sentence_index = len(questions) + i
                    if sentence_index < len(key_sentences):
                        try:
                            question = self.generate_multiple_choice_question(key_sentences[sentence_index])
                            if question:
                                questions.append(question)
                        except Exception as e:
                            logger.error(f"Ошибка при генерации вопроса с множественным выбором: {str(e)}")
                            continue
            except Exception as e:
                logger.error(f"Ошибка в блоке генерации вопросов с множественным выбором: {str(e)}")
            
            # Генерация вопросов правда/ложь
            try:
                for i in range(min(question_types['true_false'], len(key_sentences) - len(questions))):
                    sentence_index = len(questions) + i
                    if sentence_index < len(key_sentences):
                        try:
                            question = self.generate_true_false_question(key_sentences[sentence_index])
                            if question:
                                questions.append(question)
                        except Exception as e:
                            logger.error(f"Ошибка при генерации вопроса правда/ложь: {str(e)}")
                            continue
            except Exception as e:
                logger.error(f"Ошибка в блоке генерации вопросов правда/ложь: {str(e)}")
            
            # Генерация вопросов с заполнением пропусков
            try:
                for i in range(min(question_types['fill_blank'], len(key_sentences) - len(questions))):
                    sentence_index = len(questions) + i
                    if sentence_index < len(key_sentences):
                        try:
                            question = self.generate_fill_blank_question(key_sentences[sentence_index])
                            if question:
                                questions.append(question)
                        except Exception as e:
                            logger.error(f"Ошибка при генерации вопроса с заполнением пропусков: {str(e)}")
                            continue
            except Exception as e:
                logger.error(f"Ошибка в блоке генерации вопросов с заполнением пропусков: {str(e)}")
            
            # Если не удалось сгенерировать нужное количество вопросов, добавляем дополнительные
            while len(questions) < num_questions and key_sentences:
                # Выбираем случайное предложение
                sentence = random.choice(key_sentences)
                
                # Пробуем сгенерировать вопрос с заполнением пропусков как наиболее надежный тип
                try:
                    question = self.generate_fill_blank_question(sentence)
                    if question and question not in questions:
                        questions.append(question)
                        continue
                except Exception as e:
                    logger.error(f"Ошибка при генерации дополнительного вопроса: {str(e)}")
                
                # Если не удалось, пробуем правда/ложь
                try:
                    question = self.generate_true_false_question(sentence)
                    if question and question not in questions:
                        questions.append(question)
                except Exception:
                    pass
        
        except Exception as e:
            logger.error(f"Общая ошибка при генерации вопросов: {str(e)}")
            # Если произошла ошибка, создаем простые вопросы
            for i in range(min(num_questions, len(key_sentences))):
                try:
                    # Создаем самый простой вопрос - с заполнением пропусков
                    question = self.generate_fill_blank_question(key_sentences[i])
                    if question:
                        questions.append(question)
                except:
                    continue
        
        # Если все еще не хватает вопросов, создаем еще самые простые
        if len(questions) < num_questions:
            logger.warning(f"Сгенерировано недостаточно вопросов ({len(questions)}). Добавляем базовые вопросы.")
            
            # Создаем простые вопросы правда/ложь
            for sentence in key_sentences:
                if len(questions) >= num_questions:
                    break
                
                try:
                    # Создаем самый простой вопрос - правда/ложь с оригинальным текстом
                    question = {
                        "question_type": "true_false",
                        "text": f"Верно ли следующее утверждение: \"{sentence.text}\"",
                        "options": ["правда", "ложь"],
                        "correct_answer": "правда"
                    }
                    
                    if question not in questions:
                        questions.append(question)
                except:
                    continue
        
        logger.info(f"Успешно сгенерировано {len(questions)} вопросов")
        return questions