create table study.comment (
  aid       integer not null,
  lid       integer not null,
  qid       integer not null,
  
  body_type text    not null,  -- 本文文字列のタイプ(plane, tex)
  body      text    not null,
  
  constraint fk_study_comment_aid_lid_qid
    foreign key (aid, lid, qid) references study.questions(aid, lid, id),
  primary key (aid, lid, qid)
);

