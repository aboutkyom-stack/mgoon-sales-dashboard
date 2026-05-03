-- 간호도 → 관여도 컬럼명 정정 (STT 오인식 정정)
-- 강의 원본 용어는 "관여도(Involvement, 1~10)"가 정확. 0 값은 1로 보정.
-- 적용 전: 백업 권장. 한글 컬럼은 따옴표 필수.

ALTER TABLE 엠군_타겟 RENAME COLUMN 간호도 TO 관여도;
UPDATE 엠군_타겟 SET 관여도 = 1 WHERE 관여도 = 0;

-- 영문 mgoon_targets는 엠군_재구축.sql 적용 시 폐기됐어야 하나, 잔존 시:
-- ALTER TABLE mgoon_targets RENAME COLUMN urgency TO involvement;
-- UPDATE mgoon_targets SET involvement = 1 WHERE involvement = 0;
