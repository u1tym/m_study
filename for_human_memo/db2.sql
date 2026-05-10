alter table study.questions add column problem_1_type text not null default 'plane'; -- 設問_Part_1のタイプ(plane/tex)
alter table study.questions add column problem_2_type text null; -- 設問_Part_2のタイプ(plane/tex)
alter table study.questions add column problem_3_type text null; -- 設問_Part_3のタイプ(plane/tex)

