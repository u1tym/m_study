from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from psycopg import Connection

from app.auth import get_current_aid
from app.db import get_db
from app.schemas import (
    AnswerQuestionRequest,
    AnswerQuestionResponse,
    CreateLectureRequest,
    CreateQuestionRequest,
    CreateTopLectureRequest,
    DeleteLectureRequest,
    DeleteQuestionRequest,
    GetQuestionResponse,
    GetQuestionResponseChoice,
    LectureListItem,
    LectureNode,
    QuestionListItem,
    QuestionListResponse,
    ResultResponse,
    SwapLectureOrderRequest,
    UpdateQuestionRequest,
)

app = FastAPI(title="Study API", version="1.0.0")


def _next_lecture_id(db: Connection, aid: int) -> int:
    cur = db.cursor()
    cur.execute("select coalesce(max(id), 0) + 1 as next_id from study.lectures where aid = %s", (aid,))
    return int(cur.fetchone()["next_id"])


def _next_lecture_order(db: Connection, aid: int, pid: int | None) -> int:
    cur = db.cursor()
    if pid is None:
        cur.execute(
            "select coalesce(max(dorder), 0) + 1 as next_order from study.lectures where aid = %s and pid is null",
            (aid,),
        )
    else:
        cur.execute(
            "select coalesce(max(dorder), 0) + 1 as next_order from study.lectures where aid = %s and pid = %s",
            (aid, pid),
        )
    return int(cur.fetchone()["next_order"])


def _next_question_id(db: Connection, aid: int, lid: int) -> int:
    cur = db.cursor()
    cur.execute(
        "select coalesce(max(id), 0) + 1 as next_id from study.questions where aid = %s and lid = %s",
        (aid, lid),
    )
    return int(cur.fetchone()["next_id"])


def _next_choice_id(db: Connection, aid: int, lid: int, qid: int) -> int:
    cur = db.cursor()
    cur.execute(
        "select coalesce(max(id), 0) + 1 as next_id from study.choice where aid = %s and lid = %s and qid = %s",
        (aid, lid, qid),
    )
    return int(cur.fetchone()["next_id"])


def _next_exam_id(db: Connection, aid: int, lid: int) -> int:
    cur = db.cursor()
    cur.execute(
        "select coalesce(max(id), 0) + 1 as next_id from study.exam where aid = %s and lid = %s",
        (aid, lid),
    )
    return int(cur.fetchone()["next_id"])


def _build_lecture_tree(db: Connection, aid: int, root_id: int) -> LectureNode:
    cur = db.cursor()
    cur.execute(
        """
        with recursive tree as (
          select aid, id, pid, dorder, title, explain_type, explain
            from study.lectures
           where aid = %s and id = %s and pid is null and is_deleted = false
          union all
          select c.aid, c.id, c.pid, c.dorder, c.title, c.explain_type, c.explain
            from study.lectures c
            join tree t on t.aid = c.aid and t.id = c.pid
           where c.is_deleted = false
        )
        select aid, id, pid, dorder, title, explain_type, explain
          from tree
         order by coalesce(pid, 0), dorder, id
        """,
        (aid, root_id),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found.")

    node_map: dict[int, LectureNode] = {}
    children: dict[int | None, list[int]] = {}
    for row in rows:
        lid = int(row["id"])
        pid = row["pid"]
        node_map[lid] = LectureNode(
            lid=lid,
            ttl=row["title"],
            typ=row["explain_type"],
            exp=row["explain"],
            chd=[],
        )
        children.setdefault(pid, []).append(lid)

    for pid, child_ids in children.items():
        if pid is None:
            continue
        parent = node_map.get(int(pid))
        if parent is None:
            continue
        parent.chd = [node_map[cid] for cid in child_ids]

    return node_map[root_id]


@app.post("/study/lectures/top", response_model=ResultResponse)
def create_top_lecture(
    body: CreateTopLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    lid = _next_lecture_id(db, aid)
    dorder = _next_lecture_order(db, aid, None)
    with db.transaction():
        db.execute(
            """
            insert into study.lectures (aid, id, pid, dorder, title, explain_type, explain, is_deleted)
            values (%s, %s, null, %s, %s, null, null, false)
            """,
            (aid, lid, dorder, body.lecture_name),
        )
    return ResultResponse(result=True)


@app.get("/study/lectures/top", response_model=list[LectureListItem])
def list_top_lectures(
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> list[LectureListItem]:
    cur = db.cursor()
    cur.execute(
        """
        select id, title
          from study.lectures
         where aid = %s and pid is null and is_deleted = false
         order by dorder, id
        """,
        (aid,),
    )
    return [LectureListItem(lid=int(row["id"]), ttl=row["title"]) for row in cur.fetchall()]


@app.post("/study/lectures/top/delete", response_model=ResultResponse)
def delete_top_lecture(
    body: DeleteLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    with db.transaction():
        cur = db.execute(
            "update study.lectures set is_deleted = true where aid = %s and id = %s",
            (aid, body.lid),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found.")
    return ResultResponse(result=True)


@app.post("/study/lectures/child", response_model=ResultResponse)
def create_child_lecture(
    body: CreateLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    lid = _next_lecture_id(db, aid)
    dorder = _next_lecture_order(db, aid, body.parent_lid)
    with db.transaction():
        db.execute(
            """
            insert into study.lectures (aid, id, pid, dorder, title, explain_type, explain, is_deleted)
            values (%s, %s, %s, %s, %s, %s, %s, false)
            """,
            (aid, lid, body.parent_lid, dorder, body.title, body.explain_type, body.explain),
        )
    return ResultResponse(result=True)


@app.post("/study/lectures/swap-order", response_model=ResultResponse)
def swap_lecture_order(
    body: SwapLectureOrderRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    cur = db.cursor()
    cur.execute(
        "select id, dorder from study.lectures where aid = %s and id in (%s, %s) for update",
        (aid, body.lid_1, body.lid_2),
    )
    rows = cur.fetchall()
    if len(rows) != 2:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found.")

    first = next(row for row in rows if int(row["id"]) == body.lid_1)
    second = next(row for row in rows if int(row["id"]) == body.lid_2)
    with db.transaction():
        db.execute(
            "update study.lectures set dorder = -1 where aid = %s and id = %s",
            (aid, body.lid_1),
        )
        db.execute(
            "update study.lectures set dorder = %s where aid = %s and id = %s",
            (int(first["dorder"]), aid, body.lid_2),
        )
        db.execute(
            "update study.lectures set dorder = %s where aid = %s and id = %s",
            (int(second["dorder"]), aid, body.lid_1),
        )
    return ResultResponse(result=True)


@app.post("/study/lectures/delete", response_model=ResultResponse)
def delete_lecture(
    body: DeleteLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    with db.transaction():
        cur = db.execute(
            "update study.lectures set is_deleted = true where aid = %s and id = %s",
            (aid, body.lid),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found.")
    return ResultResponse(result=True)


@app.get("/study/lectures/tree/{lid}", response_model=LectureNode)
def get_lecture_tree(
    lid: int,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> LectureNode:
    return _build_lecture_tree(db, aid, lid)


def _insert_question(
    db: Connection,
    aid: int,
    body: CreateQuestionRequest,
) -> None:
    qid = _next_question_id(db, aid, body.lid)
    num_ans = sum(1 for choice in body.choices if choice.is_right)
    db.execute(
        """
        insert into study.questions (
          aid, lid, id, title, problem_1, image_1_b64, problem_2, image_2_b64, problem_3, num_ans, is_deleted
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
        """,
        (aid, body.lid, qid, body.ttl, body.pb1, body.im1, body.pb2, body.im2, body.pb3, num_ans),
    )

    next_choice_id = _next_choice_id(db, aid, body.lid, qid)
    for choice in body.choices:
        cid = next_choice_id
        next_choice_id += 1
        db.execute(
            """
            insert into study.choice (aid, lid, qid, id, option_type, option, image_b64)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (aid, body.lid, qid, cid, choice.typ, choice.opt, choice.img),
        )
        if choice.is_right:
            db.execute(
                "insert into study.answer (aid, lid, qid, cid) values (%s, %s, %s, %s)",
                (aid, body.lid, qid, cid),
            )


@app.post("/study/questions", response_model=ResultResponse)
def create_question(
    body: CreateQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    with db.transaction():
        _insert_question(db, aid, body)
    return ResultResponse(result=True)


@app.post("/study/questions/delete", response_model=ResultResponse)
def delete_question(
    body: DeleteQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    with db.transaction():
        cur = db.execute(
            "update study.questions set is_deleted = true where aid = %s and lid = %s and id = %s",
            (aid, body.lid, body.qid),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")
    return ResultResponse(result=True)


@app.post("/study/questions/update", response_model=ResultResponse)
def update_question(
    body: UpdateQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    create_body = CreateQuestionRequest(
        lid=body.lid,
        ttl=body.ttl,
        pb1=body.pb1,
        im1=body.im1,
        pb2=body.pb2,
        im2=body.im2,
        pb3=body.pb3,
        choices=body.choices,
    )
    with db.transaction():
        db.execute(
            "update study.questions set is_deleted = true where aid = %s and lid = %s and id = %s",
            (aid, body.lid, body.qid),
        )
        _insert_question(db, aid, create_body)
    return ResultResponse(result=True)


@app.get("/study/questions/{lid}", response_model=QuestionListResponse)
def list_questions(
    lid: int,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> QuestionListResponse:
    cur = db.cursor()
    cur.execute(
        """
        select id, title
          from study.questions
         where aid = %s and lid = %s and is_deleted = false
         order by id
        """,
        (aid, lid),
    )
    return QuestionListResponse(
        lid=lid,
        qes=[QuestionListItem(qid=int(row["id"]), ttl=row["title"]) for row in cur.fetchall()],
    )


@app.get("/study/questions/{lid}/{qid}", response_model=GetQuestionResponse)
def get_question(
    lid: int,
    qid: int,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> GetQuestionResponse:
    use_qid = qid
    cur = db.cursor()
    if qid < 0:
        cur.execute(
            """
            select id
              from study.questions
             where aid = %s and lid = %s and is_deleted = false
             order by random()
             limit 1
            """,
            (aid, lid),
        )
        pick = cur.fetchone()
        if pick is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")
        use_qid = int(pick["id"])

    cur.execute(
        """
        select aid, lid, id, title, problem_1, image_1_b64, problem_2, image_2_b64, problem_3, num_ans
          from study.questions
         where aid = %s and lid = %s and id = %s and is_deleted = false
        """,
        (aid, lid, use_qid),
    )
    question = cur.fetchone()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")

    cur.execute(
        """
        select id, option_type, option, image_b64
          from study.choice
         where aid = %s and lid = %s and qid = %s
         order by id
        """,
        (aid, lid, use_qid),
    )
    options = [
        GetQuestionResponseChoice(
            cid=int(row["id"]),
            typ=row["option_type"],
            opt=row["option"],
            img=row["image_b64"],
        )
        for row in cur.fetchall()
    ]

    return GetQuestionResponse(
        lid=int(question["lid"]),
        ttl=question["title"],
        pb1=question["problem_1"],
        im1=question["image_1_b64"],
        pb2=question["problem_2"],
        im2=question["image_2_b64"],
        pb3=question["problem_3"],
        num=int(question["num_ans"]),
        opt=options,
    )


@app.post("/study/questions/answer", response_model=AnswerQuestionResponse)
def answer_question(
    body: AnswerQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> AnswerQuestionResponse:
    cur = db.cursor()
    cur.execute(
        "select cid from study.answer where aid = %s and lid = %s and qid = %s order by cid",
        (aid, body.lid, body.qid),
    )
    right = [int(row["cid"]) for row in cur.fetchall()]
    answer_sorted = sorted(set(body.answer))
    is_right = answer_sorted == right

    with db.transaction():
        eid = _next_exam_id(db, aid, body.lid)
        db.execute(
            """
            insert into study.exam (aid, lid, id, q_time, qid, is_right)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (aid, body.lid, eid, datetime.now(), body.qid, is_right),
        )

    return AnswerQuestionResponse(result=is_right, right=right)

