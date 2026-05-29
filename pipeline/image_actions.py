"""이미지 갤러리/리스트 공통 액션 (새로고침, 다운로드).

3곳에서 사용:
  - pages/2_product_edit.py  — 제품 이미지 영역
  - pages/3_gallery.py Tab 1 — DB 이미지
  - pages/3_gallery.py Tab 2 — Drive 탐색 이미지 그리드

설계 메모:
  - 썸네일 cache-bust: scope_key별 카운터를 session_state에 두고, URL에 &v={N} 부착
    → 새로고침 버튼이 카운터를 증가시키면 브라우저가 URL을 새로 받아 깨진 썸네일도 다시 요청
  - 개별 다운로드: Drive `uc?export=download` 직링크 (서버 부하 0, 브라우저가 직접 받음)
  - 일괄 다운로드: Drive에서 바이트 받아 메모리 ZIP → st.download_button
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

import streamlit as st


# ── 썸네일 URL (cache-bust 지원) ────────────────────────────
def _thumb_version(scope_key: str) -> int:
    return st.session_state.get(f"_thumb_ver_{scope_key}", 0)


def thumbnail_url(drive_file_id: str, size: int = 400, scope_key: str | None = None) -> str:
    """Google Drive 썸네일 URL. scope_key가 주어지면 그 scope의 새로고침 버전을 query에 부착."""
    base = f"https://drive.google.com/thumbnail?id={drive_file_id}&sz=w{size}"
    if scope_key:
        v = _thumb_version(scope_key)
        if v:
            return f"{base}&v={v}"
    return base


def original_view_url(drive_file_id: str) -> str:
    """Drive 원본 보기 URL — 표준 Drive 보기 페이지.

    `file/d/{fid}/view`는 이미지·동영상·txt·pdf 등 모든 파일 타입을
    Drive UI 안에서 인라인 미리보기로 표시한다 (다운로드 강제 X).
    """
    return f"https://drive.google.com/file/d/{drive_file_id}/view"


# ── 기타 파일 아이콘 매핑 ──────────────────────────────────
_FILE_ICON_BY_EXT: dict[str, str] = {
    "pdf": "📄",
    "doc": "📝", "docx": "📝", "hwp": "📝", "txt": "📝", "md": "📝",
    "xls": "📊", "xlsx": "📊", "csv": "📊",
    "ppt": "📽️", "pptx": "📽️",
    "mp3": "🎵", "wav": "🎵", "flac": "🎵", "m4a": "🎵", "ogg": "🎵",
    "zip": "📦", "rar": "📦", "7z": "📦", "tar": "📦", "gz": "📦",
    "psd": "🎨", "ai": "🎨", "sketch": "🎨", "xd": "🎨",
    "json": "🔧", "xml": "🔧", "yaml": "🔧", "yml": "🔧",
    "html": "🌐", "htm": "🌐",
}


def file_icon_for_name(filename: str) -> str:
    """파일명에서 확장자를 추출해 아이콘 문자열 반환. 매칭 안되면 📎."""
    if not filename or "." not in filename:
        return "📎"
    ext = filename.rsplit(".", 1)[1].lower()
    return _FILE_ICON_BY_EXT.get(ext, "📎")


def file_icon_card(
    drive_file_id: str,
    filename: str,
    aspect_ratio: float = 1.0,
) -> None:
    """이미지/비디오가 아닌 기타 파일을 큰 아이콘 + 파일명 카드로 표시."""
    import html

    icon = file_icon_for_name(filename)
    name_safe = html.escape(filename)
    # 정사각형 비율 유지 (썸네일 그리드와 같은 카드 크기)
    pad_pct = 100 / aspect_ratio
    st.markdown(
        f"""
        <div style="width:100%; position:relative; padding-top:{pad_pct}%;
                    background:#222; border-radius:4px; overflow:hidden;">
          <div style="position:absolute; top:0; left:0; width:100%; height:100%;
                      display:flex; flex-direction:column; align-items:center; justify-content:center;
                      gap:8px;">
            <div style="font-size:48px; line-height:1;">{icon}</div>
            <div style="font-size:11px; color:#bbb; padding:0 8px; text-align:center;
                        word-break:break-all; max-height:40%; overflow:hidden;">
              {name_safe}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def video_thumb_with_play_overlay(
    drive_file_id: str,
    size: int = 400,
    scope_key: str | None = None,
    alt: str = "",
) -> None:
    """동영상 썸네일 + ▶ 재생 배지 오버레이. 클릭 시 새 탭으로 Drive 재생 페이지 열림.

    설계 메모:
      - 카드 전체를 <a target="_blank">로 감싸 ▶ 클릭 시 Drive 보기 페이지(file/d/{fid}/view)
        로 이동 → 거기서 실제 재생 가능.
      - 썸네일 실패(onerror) 시 view URL로 폴백하면 빈 비디오 플레이어가 보임 → 차라리
        img를 숨겨 회색 카드 배경 + ▶만 남기는 게 깔끔.
      - 정사각 비율(aspect-ratio: 1/1)로 컬럼 크기 일관성 유지 (썸네일 못 받았을 때 카드가
        쪼그라드는 것 방지).
    """
    import html

    thumb = thumbnail_url(drive_file_id, size, scope_key)
    href = original_view_url(drive_file_id)
    alt_safe = html.escape(alt or "")

    st.markdown(
        f"""
        <a href="{href}" target="_blank" rel="noopener"
           style="display:block; text-decoration:none;">
          <div style="position:relative; width:100%; aspect-ratio:1/1;
                      background:#222; border-radius:4px; overflow:hidden;">
            <img src="{thumb}"
                 alt="{alt_safe}"
                 loading="lazy"
                 onerror="this.onerror=null;this.style.display='none';"
                 style="position:absolute; inset:0; width:100%; height:100%;
                        object-fit:cover; display:block;" />
            <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%);
                        font-size:42px; color:white; text-shadow:0 2px 8px rgba(0,0,0,0.9);
                        line-height:1; pointer-events:none;">
              ▶
            </div>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )


def image_with_fallback(
    drive_file_id: str,
    size: int = 400,
    scope_key: str | None = None,
    alt: str = "",
    caption: str | None = None,
) -> None:
    """st.image 대체 — Drive 썸네일 시도 → 실패 시 원본 URL로 자동 폴백.

    Drive 썸네일은 일부 파일(webp, 대용량, 비표준 jpg 등)에 대해 생성이 실패하거나
    매우 늦게 생성됨. 그 경우 <img>의 onerror 핸들러가 view URL로 src를 교체한다.

    페이지가 재로드될 때마다 다시 썸네일 URL을 먼저 시도하므로, Drive가 그 사이
    썸네일 생성에 성공했다면 다음 방문 때 자동으로 가벼운 썸네일로 복귀한다.
    """
    import html

    thumb = thumbnail_url(drive_file_id, size, scope_key)
    fallback = original_view_url(drive_file_id)
    alt_safe = html.escape(alt or "")

    # this.onerror=null — view URL도 실패 시 무한 루프 방지
    st.markdown(
        f"""
        <img src="{thumb}"
             alt="{alt_safe}"
             loading="lazy"
             onerror="this.onerror=null;this.src='{fallback}';"
             style="width:100%; height:auto; display:block; border-radius:4px; background:#222;" />
        """,
        unsafe_allow_html=True,
    )
    if caption:
        st.caption(caption)


# ── 새로고침 버튼 ───────────────────────────────────────────
def refresh_button(
    scope_key: str,
    label: str = "🔄 새로고침",
    help: str | None = None,
    use_container_width: bool = False,
) -> bool:
    """DB 캐시 클리어 + 썸네일 버전 증가 + rerun.

    scope_key: 페이지/탭별 고유 식별자 (썸네일 cache-bust 카운터의 키).
    """
    clicked = st.button(
        label,
        key=f"refresh_btn_{scope_key}",
        help=help or "DB 다시 조회 + 이미지 캐시 갱신",
        use_container_width=use_container_width,
    )
    if clicked:
        try:
            st.cache_data.clear()
        except Exception:
            pass
        k = f"_thumb_ver_{scope_key}"
        st.session_state[k] = st.session_state.get(k, 0) + 1
        st.rerun()
    return clicked


# ── 개별 다운로드 링크 (브라우저 직접) ──────────────────────
def individual_download_link(drive_file_id: str, label: str = "⬇️ 다운로드") -> str:
    """Drive 직접 다운로드 markdown 링크. 브라우저가 Drive에서 직접 받음 (서버 부하 0)."""
    url = f"https://drive.google.com/uc?export=download&id={drive_file_id}"
    return f"[{label}]({url})"


# ── 일괄 ZIP 다운로드 ──────────────────────────────────────
def bulk_download_zip(
    files: list[dict],
    scope_key: str,
    zip_name_prefix: str = "images",
    default_account: str | None = None,
    extra_files: list[dict] | None = None,
    extra_label: str = "동영상",
) -> None:
    """일괄 ZIP 다운로드 UI.

    files: 기본 포함 파일 (예: 이미지)
    extra_files: 토글로 ON/OFF 가능한 추가 파일 (예: 동영상). None이면 토글 없음.
    extra_label: 토글 라벨에 표시될 이름 (예: "동영상")

    files/extra_files 항목 스키마:
      {"드라이브_파일_id" or "id": ..., "파일명" or "name": ..., "계정"(optional): ...}
    scope_key: session_state 키 분리용
    default_account: 파일에 "계정" 필드가 없을 때 사용할 fallback 계정 라벨
    """
    if not files and not extra_files:
        return

    # 동영상 포함 토글 (extra_files가 있을 때만)
    include_extra = False
    if extra_files:
        include_extra = st.checkbox(
            f"🎬 {extra_label} 포함 ({len(extra_files)}개)",
            value=False,
            key=f"zip_include_extra_{scope_key}",
            help=f"체크하면 {extra_label} 파일도 ZIP에 함께 포함합니다.",
        )

    # 실제 ZIP 대상
    target_files = list(files)
    if include_extra and extra_files:
        target_files.extend(extra_files)

    if not target_files:
        return

    # 계정별로 그룹화 (한 ZIP에 여러 계정 파일이 섞일 수 있음 → 계정별로 service 빌드)
    files_by_account: dict[str, list[dict]] = {}
    for f in target_files:
        acc = f.get("계정") or default_account or ""
        if not acc:
            continue
        files_by_account.setdefault(acc, []).append(f)

    if not files_by_account:
        st.caption("⚠️ 계정 정보가 없어 일괄 다운로드를 만들 수 없습니다.")
        return

    zip_btn_key   = f"build_zip_{scope_key}"
    zip_data_key  = f"_zip_data_{scope_key}"
    zip_name_key  = f"_zip_name_{scope_key}"
    zip_fail_key  = f"_zip_fail_{scope_key}"

    _label_suffix = f" + {extra_label}" if include_extra and extra_files else ""
    if st.button(
        f"📦 전체 다운로드 ZIP 만들기 ({len(target_files)}개{_label_suffix})",
        key=zip_btn_key,
        help="대상 파일을 ZIP으로 묶어 다운로드 준비",
    ):
        with st.spinner(f"{len(target_files)}개 다운로드 + 압축 중…"):
            buf = io.BytesIO()
            all_failed: list[str] = []
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                try:
                    from pipeline.drive_client import build_service, download_file
                except ImportError as e:
                    st.error(f"Drive 클라이언트 로드 실패: {e}")
                    return

                used_names: set[str] = set()
                for acc_label, acc_files in files_by_account.items():
                    try:
                        service = build_service(acc_label)
                    except Exception as e:
                        all_failed.append(f"[계정 {acc_label}] service 빌드 실패: {e}")
                        continue
                    for f in acc_files:
                        fid = f.get("드라이브_파일_id") or f.get("id")
                        fname = f.get("파일명") or f.get("name") or f"{fid}.bin"
                        if not fid:
                            continue
                        # 중복 파일명 방지 (계정 prefix 부여)
                        candidate = fname
                        n = 1
                        while candidate in used_names:
                            stem, _, ext = fname.rpartition(".")
                            candidate = f"{stem}_{n}.{ext}" if stem else f"{fname}_{n}"
                            n += 1
                        used_names.add(candidate)
                        try:
                            data, _mime = download_file(service, fid)
                            zf.writestr(candidate, data)
                        except Exception as e:
                            all_failed.append(f"{candidate} ({type(e).__name__}: {e})")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.session_state[zip_data_key] = buf.getvalue()
            st.session_state[zip_name_key] = f"{zip_name_prefix}_{ts}.zip"
            st.session_state[zip_fail_key] = all_failed
        st.rerun()

    # ZIP 준비됐으면 download_button + 결과 표시
    if zip_data_key in st.session_state:
        zip_bytes = st.session_state[zip_data_key]
        size_kb = len(zip_bytes) // 1024
        st.download_button(
            label=f"💾 ZIP 저장 ({size_kb:,} KB)",
            data=zip_bytes,
            file_name=st.session_state[zip_name_key],
            mime="application/zip",
            key=f"dl_zip_{scope_key}",
        )
        failed = st.session_state.get(zip_fail_key) or []
        if failed:
            with st.expander(f"⚠️ 실패 {len(failed)}건"):
                for line in failed:
                    st.caption(line)
