from pydantic import BaseModel, Field


class ResultResponse(BaseModel):
    result: bool


class CreateTopLectureRequest(BaseModel):
    lecture_name: str = Field(min_length=1)


class LectureListItem(BaseModel):
    lid: int
    ttl: str | None


class DeleteLectureRequest(BaseModel):
    lid: int


class CreateLectureRequest(BaseModel):
    parent_lid: int
    title: str | None = None
    explain_type: str | None = None
    explain: str | None = None


class SwapLectureOrderRequest(BaseModel):
    lid_1: int
    lid_2: int


class LectureNode(BaseModel):
    lid: int
    ttl: str | None
    typ: str | None
    exp: str | None
    chd: list["LectureNode"]


class ChoiceInput(BaseModel):
    typ: str | None = None
    opt: str | None = None
    img: str | None = None
    is_right: bool


class CreateQuestionRequest(BaseModel):
    lid: int
    ttl: str | None = None
    pb1: str = Field(min_length=1)
    im1: str | None = None
    pb2: str | None = None
    im2: str | None = None
    pb3: str | None = None
    choices: list[ChoiceInput] = Field(min_length=1)


class DeleteQuestionRequest(BaseModel):
    lid: int
    qid: int


class UpdateQuestionRequest(CreateQuestionRequest):
    qid: int


class QuestionListItem(BaseModel):
    qid: int
    ttl: str | None


class QuestionListResponse(BaseModel):
    lid: int
    qes: list[QuestionListItem]


class GetQuestionResponseChoice(BaseModel):
    cid: int
    typ: str | None
    opt: str | None
    img: str | None
    is_right: bool


class GetQuestionResponse(BaseModel):
    lid: int
    ttl: str | None
    pb1: str
    im1: str | None
    pb2: str | None
    im2: str | None
    pb3: str | None
    num: int
    opt: list[GetQuestionResponseChoice]


class AnswerQuestionRequest(BaseModel):
    lid: int
    qid: int
    answer: list[int] = Field(min_length=1)


class AnswerQuestionResponse(BaseModel):
    result: bool
    right: list[int]
