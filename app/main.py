from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from psycopg import Connection
from starlette.responses import Response

from app.auth import get_current_aid
from app.db import get_db
from app.logging_setup import configure_logging
from app.middleware.api_logging import APILoggingMiddleware
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

_api_logger = logging.getLogger("study.api")


def _log_db_write(
    op: str,
    table: str,
    aid: int,
    rowcount: int,
    *,
    expect_rowcount: int | None = None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "event": "db_write",
        "op": op,
        "table": table,
        "aid": aid,
        "rowcount": rowcount,
        **extra,
    }
    line = json.dumps(payload, ensure_ascii=False, default=str)
    if expect_rowcount is not None and rowcount != expect_rowcount:
        _api_logger.warning(line)
    else:
        _api_logger.info(line)


def _log_db_read(table: str, aid: int, rowcount: int, **extra: Any) -> None:
    _api_logger.info(
        json.dumps(
            {"event": "db_read", "table": table, "aid": aid, "rowcount": rowcount, **extra},
            ensure_ascii=False,
            default=str,
        )
    )


def _log_question_bundle_insert(aid: int, ins: dict[str, Any], expected_choices: int) -> None:
    parts = {
        "study.questions": ins["question_rowcount"],
        "study.choice": ins["choice_rowcount"],
        "study.answer": ins["answer_rowcount"],
    }
    line = json.dumps(
        {
            "event": "db_write",
            "op": "insert",
            "table": "study.questions_bundle",
            "aid": aid,
            "lid": ins["lid"],
            "qid": ins["qid"],
            "rowcounts_by_table": parts,
            "expected_choices": expected_choices,
        },
        ensure_ascii=False,
        default=str,
    )
    bad = ins["question_rowcount"] != 1 or ins["choice_rowcount"] != expected_choices
    if bad:
        _api_logger.warning(line)
    else:
        _api_logger.info(line)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="Study API", version="1.0.0", lifespan=_lifespan)
app.add_middleware(APILoggingMiddleware)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if exc.status_code >= 500:
        body = getattr(request.state, "log_request_body", None)
        _api_logger.error(
            json.dumps(
                {
                    "event": "server_http_exception",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                    "request_body": body,
                },
                ensure_ascii=False,
                default=str,
            )
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    body = getattr(request.state, "log_request_body", None)
    _api_logger.error(
        json.dumps(
            {
                "event": "unhandled_exception",
                "method": request.method,
                "path": request.url.path,
                "request_body": body,
                "reason": str(exc),
                "exc_type": type(exc).__name__,
            },
            ensure_ascii=False,
            default=str,
        ),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


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
    cur = db.execute(
        """
        insert into study.lectures (aid, id, pid, dorder, title, explain_type, explain, is_deleted)
        values (%s, %s, null, %s, %s, null, null, false)
        """,
        (aid, lid, dorder, body.lecture_name),
    )
    _log_db_write(
        "insert",
        "study.lectures",
        aid,
        cur.rowcount,
        expect_rowcount=1,
        lid=lid,
        dorder=dorder,
        pid=None,
        title=body.lecture_name,
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
    rows = cur.fetchall()
    out = [LectureListItem(lid=int(row["id"]), ttl=row["title"]) for row in rows]
    _log_db_read("study.lectures(top)", aid, len(out), lids=[int(r["id"]) for r in rows])
    return out


@app.post("/study/lectures/top/delete", response_model=ResultResponse)
def delete_top_lecture(
    body: DeleteLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    cur = db.execute(
        "update study.lectures set is_deleted = true where aid = %s and id = %s",
        (aid, body.lid),
    )
    _log_db_write(
        "update",
        "study.lectures",
        aid,
        cur.rowcount,
        expect_rowcount=1,
        lid=body.lid,
        scope="top_soft_delete",
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
    cur = db.execute(
        """
        insert into study.lectures (aid, id, pid, dorder, title, explain_type, explain, is_deleted)
        values (%s, %s, %s, %s, %s, %s, %s, false)
        """,
        (aid, lid, body.parent_lid, dorder, body.title, body.explain_type, body.explain),
    )
    _log_db_write(
        "insert",
        "study.lectures",
        aid,
        cur.rowcount,
        expect_rowcount=1,
        lid=lid,
        dorder=dorder,
        pid=body.parent_lid,
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
    c1 = db.execute(
        "update study.lectures set dorder = -1 where aid = %s and id = %s",
        (aid, body.lid_1),
    )
    c2 = db.execute(
        "update study.lectures set dorder = %s where aid = %s and id = %s",
        (int(first["dorder"]), aid, body.lid_2),
    )
    c3 = db.execute(
        "update study.lectures set dorder = %s where aid = %s and id = %s",
        (int(second["dorder"]), aid, body.lid_1),
    )
    _log_db_write(
        "update",
        "study.lectures",
        aid,
        c1.rowcount + c2.rowcount + c3.rowcount,
        expect_rowcount=3,
        lid_1=body.lid_1,
        lid_2=body.lid_2,
        scope="swap_order",
        rowcounts=(c1.rowcount, c2.rowcount, c3.rowcount),
    )
    return ResultResponse(result=True)


@app.post("/study/lectures/delete", response_model=ResultResponse)
def delete_lecture(
    body: DeleteLectureRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    cur = db.execute(
        "update study.lectures set is_deleted = true where aid = %s and id = %s",
        (aid, body.lid),
    )
    _log_db_write(
        "update",
        "study.lectures",
        aid,
        cur.rowcount,
        expect_rowcount=1,
        lid=body.lid,
        scope="soft_delete",
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
) -> dict[str, Any]:
    qid = _next_question_id(db, aid, body.lid)
    num_ans = sum(1 for choice in body.choices if choice.is_right)
    cur_q = db.execute(
        """
        insert into study.questions (
          aid, lid, id, title, problem_1, image_1_b64, problem_2, image_2_b64, problem_3, num_ans, is_deleted
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
        """,
        (aid, body.lid, qid, body.ttl, body.pb1, body.im1, body.pb2, body.im2, body.pb3, num_ans),
    )

    next_choice_id = _next_choice_id(db, aid, body.lid, qid)
    choice_rc = 0
    answer_rc = 0
    for choice in body.choices:
        cid = next_choice_id
        next_choice_id += 1
        cur_c = db.execute(
            """
            insert into study.choice (aid, lid, qid, id, option_type, option, image_b64)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (aid, body.lid, qid, cid, choice.typ, choice.opt, choice.img),
        )
        choice_rc += cur_c.rowcount
        if choice.is_right:
            cur_a = db.execute(
                "insert into study.answer (aid, lid, qid, cid) values (%s, %s, %s, %s)",
                (aid, body.lid, qid, cid),
            )
            answer_rc += cur_a.rowcount
    if body.comment_type is not None:
        db.execute(
            """
            insert into study.comment (aid, lid, qid, body_type, body)
            values (%s, %s, %s, %s, %s)
            """,
            (aid, body.lid, qid, body.comment_type.strip(), body.comment_body),
        )
    return {
        "qid": qid,
        "question_rowcount": cur_q.rowcount,
        "choice_rowcount": choice_rc,
        "answer_rowcount": answer_rc,
        "lid": body.lid,
    }


@app.post("/study/questions", response_model=ResultResponse)
def create_question(
    body: CreateQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    ins = _insert_question(db, aid, body)
    _log_question_bundle_insert(aid, ins, len(body.choices))
    return ResultResponse(result=True)


@app.post("/study/questions/delete", response_model=ResultResponse)
def delete_question(
    body: DeleteQuestionRequest,
    db: Connection = Depends(get_db),
    aid: int = Depends(get_current_aid),
) -> ResultResponse:
    db.execute(
        "delete from study.comment where aid = %s and lid = %s and qid = %s",
        (aid, body.lid, body.qid),
    )
    cur = db.execute(
        "update study.questions set is_deleted = true where aid = %s and lid = %s and id = %s",
        (aid, body.lid, body.qid),
    )
    _log_db_write(
        "update",
        "study.questions",
        aid,
        cur.rowcount,
        expect_rowcount=1,
        lid=body.lid,
        qid=body.qid,
        scope="soft_delete",
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
        comment_type=body.comment_type,
        comment_body=body.comment_body,
        choices=body.choices,
    )
    db.execute(
        "delete from study.comment where aid = %s and lid = %s and qid = %s",
        (aid, body.lid, body.qid),
    )
    cur_del = db.execute(
        "update study.questions set is_deleted = true where aid = %s and lid = %s and id = %s",
        (aid, body.lid, body.qid),
    )
    ins = _insert_question(db, aid, create_body)
    _log_db_write(
        "update",
        "study.questions",
        aid,
        cur_del.rowcount,
        expect_rowcount=1,
        lid=body.lid,
        qid=body.qid,
        scope="soft_delete_for_replace",
    )
    _log_question_bundle_insert(aid, ins, len(create_body.choices))
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
    rows = cur.fetchall()
    qes = [QuestionListItem(qid=int(row["id"]), ttl=row["title"]) for row in rows]
    _log_db_read("study.questions(by_lid)", aid, len(qes), lid=lid, qids=[int(r["id"]) for r in rows])
    return QuestionListResponse(lid=lid, qes=qes)


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
        select c.id, c.option_type, c.option, c.image_b64,
               exists (
                 select 1 from study.answer a
                  where a.aid = c.aid and a.lid = c.lid and a.qid = c.qid and a.cid = c.id
               ) as is_right
          from study.choice c
         where c.aid = %s and c.lid = %s and c.qid = %s
         order by c.id
        """,
        (aid, lid, use_qid),
    )
    options = [
        GetQuestionResponseChoice(
            cid=int(row["id"]),
            typ=row["option_type"],
            opt=row["option"],
            img=row["image_b64"],
            is_right=bool(row["is_right"]),
        )
        for row in cur.fetchall()
    ]

    cur.execute(
        "select body_type, body from study.comment where aid = %s and lid = %s and qid = %s",
        (aid, lid, use_qid),
    )
    cmt = cur.fetchone()

    return GetQuestionResponse(
        lid=int(question["lid"]),
        ttl=question["title"],
        pb1=question["problem_1"],
        im1=question["image_1_b64"],
        pb2=question["problem_2"],
        im2=question["image_2_b64"],
        pb3=question["problem_3"],
        comment_type=cmt["body_type"] if cmt else None,
        comment_body=cmt["body"] if cmt else None,
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

    eid = _next_exam_id(db, aid, body.lid)
    cur_ex = db.execute(
        """
        insert into study.exam (aid, lid, id, q_time, qid, is_right)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (aid, body.lid, eid, datetime.now(), body.qid, is_right),
    )
    _log_db_write(
        "insert",
        "study.exam",
        aid,
        cur_ex.rowcount,
        expect_rowcount=1,
        lid=body.lid,
        eid=eid,
        qid=body.qid,
        is_right=is_right,
    )

    cur.execute(
        "select body_type, body from study.comment where aid = %s and lid = %s and qid = %s",
        (aid, body.lid, body.qid),
    )
    cmt = cur.fetchone()

    return AnswerQuestionResponse(
        result=is_right,
        right=right,
        comment_type=cmt["body_type"] if cmt else None,
        comment_body=cmt["body"] if cmt else None,
    )

