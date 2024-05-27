!pip install transformers torch numpy en-core-web-sm datasets
!python -m spacy download en_core_web_sm

import en_core_web_sm
import json
import numpy as np
import random
import re
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    AutoModelForSequenceClassification,
)
from typing import Any, List, Mapping, Tuple

class QuestionGenerator:
    def __init__(self) -> None:
        QG_PRETRAINED = "iarfmoose/t5-base-question-generator"
        self.ANSWER_TOKEN = "<answer>"
        self.CONTEXT_TOKEN = "<context>"
        self.SEQ_LENGTH = 512

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.qg_tokenizer = AutoTokenizer.from_pretrained(QG_PRETRAINED, use_fast=False)
        self.qg_model = AutoModelForSeq2SeqLM.from_pretrained(QG_PRETRAINED)
        self.qg_model.to(self.device)
        self.qg_model.eval()

        self.qa_evaluator = QAEvaluator()

    def generate(
        self,
        article: str,
        use_evaluator: bool = True,
        num_questions: int = None,
        answer_style: str = "all"
    ) -> List:
        print("Generating questions...\n")

        qg_inputs, qg_answers = self.generate_qg_inputs(article, answer_style)
        print(f"Generated QG Inputs: {qg_inputs[:2]}")
        print(f"Generated QG Answers: {qg_answers[:2]}")

        generated_questions = self.generate_questions_from_inputs(qg_inputs)

        message = "{} questions don't match {} answers".format(
            len(generated_questions), len(qg_answers)
        )
        assert len(generated_questions) == len(qg_answers), message

        if use_evaluator:
            print("Evaluating QA pairs...\n")
            string_encoded_qa_pairs = self.qa_evaluator.encode_qa_pairs(
                [q for q, a in zip(generated_questions, qg_answers) if isinstance(a, str)],
                [a for a in qg_answers if isinstance(a, str)]
            )
            print(f"Encoded QA Pairs: {string_encoded_qa_pairs[:2]}")
            scores = self.qa_evaluator.get_scores(string_encoded_qa_pairs)

            if num_questions:
                qa_list = self._get_ranked_qa_pairs(generated_questions, qg_answers, scores, num_questions)
            else:
                qa_list = self._get_ranked_qa_pairs(generated_questions, qg_answers, scores)
        else:
            print("Skipping evaluation step.\n")
            qa_list = self._get_all_qa_pairs(generated_questions, qg_answers)

        return qa_list

    def generate_qg_inputs(self, text: str, answer_style: str) -> Tuple[List[str], List[str]]:
        VALID_ANSWER_STYLES = ["all", "sentences", "multiple_choice"]

        if answer_style not in VALID_ANSWER_STYLES:
            raise ValueError(
                "Invalid answer style {}. Please choose from {}".format(answer_style, VALID_ANSWER_STYLES)
            )

        inputs = []
        answers = []

        if answer_style == "sentences" or answer_style == "all":
            segments = self._split_into_segments(text)

            for segment in segments:
                sentences = self._split_text(segment)
                prepped_inputs, prepped_answers = self._prepare_qg_inputs(sentences, segment)
                inputs.extend(prepped_inputs)
                answers.extend(prepped_answers)

        if answer_style == "multiple_choice" or answer_style == "all":
            sentences = self._split_text(text)
            prepped_inputs, prepped_answers = self._prepare_qg_inputs_MC(sentences)
            inputs.extend(prepped_inputs)
            answers.extend(prepped_answers)

        return inputs, answers

    def generate_questions_from_inputs(self, qg_inputs: List) -> List[str]:
        generated_questions = []
        for qg_input in qg_inputs:
            question = self._generate_question(qg_input)
            generated_questions.append(question)
        return generated_questions

    def _split_text(self, text: str) -> List[str]:
        MAX_SENTENCE_LEN = 128
        sentences = re.findall(".*?[.!\?]", text)
        cut_sentences = []

        for sentence in sentences:
            if (len(sentence) > MAX_SENTENCE_LEN):
                cut_sentences.extend(re.split("[,;:)]", sentence))

        cut_sentences = [s for s in sentences if len(s.split(" ")) > 5]
        sentences = sentences + cut_sentences

        return list(set([s.strip(" ") for s in sentences]))

    def _split_into_segments(self, text: str) -> List[str]:
        MAX_TOKENS = 490
        paragraphs = text.split("\n")
        tokenized_paragraphs = [
            self.qg_tokenizer(p)["input_ids"] for p in paragraphs if len(p) > 0
        ]
        segments = []

        while len(tokenized_paragraphs) > 0:
            segment = []
            while len(segment) < MAX_TOKENS and len(tokenized_paragraphs) > 0:
                paragraph = tokenized_paragraphs.pop(0)
                segment.extend(paragraph)
            segments.append(segment)

        return [self.qg_tokenizer.decode(s, skip_special_tokens=True) for s in segments]

    def _prepare_qg_inputs(
        self,
        sentences: List[str],
        text: str
    ) -> Tuple[List[str], List[str]]:
        inputs = []
        answers = []

        for sentence in sentences:
            qg_input = f"{self.ANSWER_TOKEN} {sentence} {self.CONTEXT_TOKEN} {text}"
            inputs.append(qg_input)
            answers.append(sentence)

        return inputs, answers

    def _prepare_qg_inputs_MC(self, sentences: List[str]) -> Tuple[List[str], List[str]]:
        spacy_nlp = en_core_web_sm.load()
        docs = list(spacy_nlp.pipe(sentences, disable=["parser"]))
        inputs_from_text = []
        answers_from_text = []

        for doc, sentence in zip(docs, sentences):
            entities = doc.ents
            if entities:
                for entity in entities:
                    qg_input = f"{self.ANSWER_TOKEN} {entity} {self.CONTEXT_TOKEN} {sentence}"
                    answers = self._get_MC_answers(entity, docs)
                    inputs_from_text.append(qg_input)
                    answers_from_text.append(answers)

        return inputs_from_text, answers_from_text

    def _get_MC_answers(self, correct_answer: Any, docs: Any) -> List[Mapping[str, Any]]:
        entities = []
        for doc in docs:
            entities.extend([{"text": e.text, "label_": e.label_} for e in doc.ents])
        entities_json = [json.dumps(kv) for kv in entities]
        pool = set(entities_json)
        num_choices = (min(4, len(pool)) - 1)
        final_choices = []
        correct_label = correct_answer.label_
        final_choices.append({"answer": correct_answer.text, "correct": True})
        pool.remove(json.dumps({"text": correct_answer.text, "label_": correct_answer.label_}))
        matches = [e for e in pool if correct_label in e]

        if len(matches) < num_choices:
            choices = matches
            pool is pool.difference(set(choices))
            choices.extend(random.sample(list(pool), num_choices - len(choices)))
        else:
            choices = random.sample(matches, num_choices)

        choices = [json.loads(s) for s in choices]

        for choice in choices:
            final_choices.append({"answer": choice["text"], "correct": False})

        random.shuffle(final_choices)
        return final_choices

    @torch.no_grad()
    def _generate_question(self, qg_input: str) -> str:
        encoded_input = self._encode_qg_input(qg_input)
        output = self.qg_model.generate(input_ids=encoded_input["input_ids"])
        question = self.qg_tokenizer.decode(output[0], skip_special_tokens=True)
        return question

    def _encode_qg_input(self, qg_input: str) -> torch.tensor:
        return self.qg_tokenizer(
            qg_input,
            padding='max_length',
            max_length=self.SEQ_LENGTH,
            truncation=True,
            return_tensors="pt",
        ).to(self.device)

    def _get_ranked_qa_pairs(
        self, generated_questions: List[str], qg_answers: List[str], scores, num_questions: int = 10
    ) -> List[Mapping[str, str]]:
        if num_questions > len(scores):
            num_questions = len(scores)
            print(("Was only able to generate {} questions. "
                  "For more questions, please input a longer text.").format(num_questions))

        ranked_outputs = []
        for i in range(num_questions):
            idx = scores[i]["idx"]
            qa_pair = {"question": generated_questions[idx], "answer": qg_answers[idx]}
            ranked_outputs.append(qa_pair)

        return ranked_outputs

    def _get_all_qa_pairs(
        self, questions: List[str], answers: List[str]
    ) -> List[Mapping[str, str]]:
        outputs = []
        for question, answer in zip(questions, answers):
            outputs.append({"question": question, "answer": answer})
        return outputs

class QAEvaluator:
    def __init__(self) -> None:
        self.qa_evaluator = "iarfmoose/bert-base-cased-qa-evaluator"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(self.qa_evaluator)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.qa_evaluator)
        self.model.to(self.device)
        self.model.eval()

    def encode_qa_pairs(self, questions: List[str], answers: List[str]) -> List[Mapping[str, Any]]:
        encoded_qa_pairs = []
        for question, answer in zip(questions, answers):
            encoded_qa = self._encode_qa(question, answer)
            encoded_qa_pairs.append(encoded_qa)
        return encoded_qa_pairs

    @torch.no_grad()
    def get_scores(self, encoded_qa_pairs: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
        scores = []
        for idx, pair in enumerate(encoded_qa_pairs):
            input_ids = pair["input_ids"]
            token_type_ids = pair["token_type_ids"]
            attention_mask = pair["attention_mask"]
            output = self.model(
                input_ids=input_ids,
                token_type_ids=token_type_ids,
                attention_mask=attention_mask,
            )
            score = output[0][0][1].item()
            pair_score = {"idx": idx, "score": score}
            scores.append(pair_score)

        return sorted(scores, key=lambda x: x["score"], reverse=True)

    def _encode_qa(self, question: str, answer: str) -> Mapping[str, torch.tensor]:
        print(f"Encoding QA Pair -> Question: {question}, Answer: {answer}")
        if not isinstance(question, str) or not isinstance(answer, str):
            raise ValueError("Both question and answer must be strings.")
        
        encoded_qa = self.tokenizer(
            question,
            answer,
            padding='max_length',
            max_length=512,
            truncation=True,
            return_tensors="pt",
        )
        return {key: tensor.to(self.device) for key, tensor in encoded_qa.items()}

def print_qa(qa_list):
    for i, qa in enumerate(qa_list):
        print("{}) {}".format(i + 1, qa["question"]))
        print("answer: {}".format(qa["answer"]))
        print("")

# Load the text from the uploaded file
with open('t.txt', 'r') as file:
    sample_text = file.read()

# Instantiate the question generator and generate questions
qg = QuestionGenerator()
questions = qg.generate(sample_text, num_questions=5, answer_style="all")
print_qa(questions)