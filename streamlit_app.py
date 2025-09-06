# streamlit_app.py — dark theme fixo + etapas + botão verde quando pronto + footer à direita
import streamlit as st
import subprocess, json, tempfile
from pathlib import Path
from typing import Optional

st.set_page_config(
    page_title="Conversor de Vídeo (Android/Windows)",
    page_icon="🎬",
    layout="wide",
)

# ============== Helpers FFmpeg ==============
def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def ffprobe_json(path: Path):
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}

def has_filter(name: str) -> bool:
    try:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return (p.returncode == 0) and (name in p.stdout)
    except Exception:
        return False

HAS_ZSCALE = has_filter("zscale")

def is_android_friendly(v: dict, a: Optional[dict]):
    ok_codec = (v.get("codec_name") == "h264")
    ok_pix   = (v.get("pix_fmt") == "yuv420p")
    ok_prof  = (v.get("profile") in ("Constrained Baseline","Baseline","Main","High"))
    ok_audio = (a is None) or (a.get("codec_name") == "aac")
    return ok_codec and ok_pix and ok_prof and ok_audio

def needs_tonemap(v: dict) -> bool:
    pix_fmt = (v.get("pix_fmt") or "").lower()
    prim = (v.get("color_primaries") or "").lower()
    xfer = (v.get("color_transfer") or "").lower()
    codec = (v.get("codec_name") or "").lower()
    profile = (v.get("profile") or "").lower()
    is10 = "10" in pix_fmt or v.get("bits_per_raw_sample") == "10"
    bt2020 = "2020" in prim or "2020" in xfer
    hevc10 = codec == "hevc" and ("10" in profile or is10)
    return bool(is10 or bt2020 or hevc10)

def build_vf(v: dict, max_h: int) -> str:
    filters = []
    if needs_tonemap(v):
        if HAS_ZSCALE:
            filters.append("zscale=t=linear:npl=100,tonemap=hable:desat=0,"
                           "zscale=matrix=bt709:transfer=bt709:primaries=bt709")
        else:
            filters.append("colorspace=all=bt709:fast=1")  # fallback sem zscale
    if max_h and max_h > 0:
        filters.append(f"scale=-2:min(ih\\,{max_h}):flags=bicubic")
    filters.append("format=yuv420p")
    return ",".join(filters)

# ============== Aparência (dark theme fixo) ==============
PRIMARY = "#915eff"
BG, PANEL, BORDER, TEXT, MUTED = "#0f1117", "#1a1f2e", "rgba(255,255,255,.12)", "#f5f7ff", "#a9b1c3"
BADGE_WAIT, BADGE_DONE, INPUT_BG = "#545b70", "#2aa84a", "#0f1117"

st.markdown(f"""
<style>
:root {{
  --bg: {BG}; --panel: {PANEL}; --border: {BORDER};
  --text: {TEXT}; --muted: {MUTED}; --primary: {PRIMARY};
}}
html, body, .block-container {{ background: var(--bg) !important; color: var(--text); }}
.block-container {{max-width: 1100px; padding-top: .6rem;}}

.frame {{
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 18px 20px;
  box-shadow: 0 10px 22px rgba(0,0,0,.12);
  background: var(--panel);
}}
.header {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.header .pill {{
  background: linear-gradient(135deg, var(--primary), #6c4ce0);
  width:34px; height:34px; border-radius:9px; display:flex; align-items:center; justify-content:center; color:white;
  box-shadow: 0 6px 18px rgba(0,0,0,.25);
}}
.subtle {{ color: var(--muted); }}

.side-card {{ border: 1px solid var(--border); border-radius: 12px; padding: 14px; background: var(--panel); }}

.steps {{ list-style:none; margin: 0; padding: 0; }}
.steps li {{ margin: 6px 0; display:flex; gap:8px; align-items:center; color: var(--text); }}
.badge {{
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%;
  font-size:.85rem; font-weight:700; color:#fff;
}}
.badge.wait {{ background:{BADGE_WAIT}; }}
.badge.run  {{ background:var(--primary); }}
.badge.done {{ background:{BADGE_DONE}; }}

.center-dl {{ display:flex; justify-content:center; margin: 14px 0 6px; }}

.footer-right {{
  display:flex; justify-content:flex-end; margin-top:14px;
}}
.footer-card {{
  text-align:right; color: var(--muted);
  line-height: 1.15; font-size:.95rem;
}}

footer {{ visibility:hidden; }}

/* Inputs com contraste */
[data-baseweb="select"]>div, .stTextInput>div>div, .stNumberInput>div>div, .stFileUploader>div {{
  background: {INPUT_BG} !important;
  border: 1px solid var(--border) !important; border-radius: 10px !important;
}}

/* Botão Converter: verde quando habilitado, cinza quando desabilitado */
#convert-btn button {{
  border-radius: 10px !important; border: 0 !important; box-shadow: 0 6px 16px rgba(0,0,0,.12);
}}
#convert-btn.ready button {{ background: #22c55e !important; color: white !important; }}
#convert-btn.notready button {{ background: #9aa0a6 !important; color: white !important; cursor:not-allowed; }}
#convert-btn.ready button:hover {{ filter: brightness(0.95); }}
</style>
""", unsafe_allow_html=True)

# ============== Layout ==============
st.markdown("<div class='frame'>", unsafe_allow_html=True)
st.markdown("""
<div class='header'>
  <div class='pill'>🎬</div>
  <div>
    <h2 style='margin:0;'>Conversor de Vídeo (Android/Windows compatível)</h2>
    <div class='subtle'>Converte para <b>H.264 + AAC</b>, <code>yuv420p</code>, com <b>faststart</b>. Detecta HDR/10-bit e aplica <i>tonemap</i> quando possível.</div>
  </div>
</div>
""", unsafe_allow_html=True)

left, right = st.columns([1.6, 1.0], vertical_alignment="top")

with left:
    file = st.file_uploader("Escolha um vídeo (até 1 GB)", type=["mp4","mov","m4v","mkv","avi","webm"])

    st.markdown("#### Opções")
    col1, col2 = st.columns(2)
    with col1:
        max_height = st.selectbox("Limitar altura", [0, 720, 1080, 1440, 2160],
                                  index=2, format_func=lambda x: "Manter" if x==0 else f"{x}p")
        preset = st.selectbox("Preset", ["fast", "medium", "slow"], index=1)
    with col2:
        cfr = st.selectbox("Travar FPS (CFR)", [0, 24, 30, 60],
                           index=0, format_func=lambda x: "Não travar" if x==0 else f"{x} fps")
        crf = st.slider("Qualidade (CRF)", 18, 26, 20)

    show_preview = st.toggle("Mostrar preview do convertido", value=False)

    st.caption("Tonemap: " + ("**zscale disponível ✅**" if HAS_ZSCALE else "**usando fallback `colorspace` ⚠️**"))

    # ===== Botão Converter (verde quando upload pronto) =====
    ready = (file is not None) and getattr(file, "size", 0) > 0
    st.markdown(f"<div id='convert-btn' class='{'ready' if ready else 'notready'}'>", unsafe_allow_html=True)
    convert_btn = st.button("Converter", use_container_width=True, disabled=not ready)
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("#### Etapas da conversão")
    st.markdown("<div class='side-card'>", unsafe_allow_html=True)
    steps_box = st.empty()
    prog_box  = st.empty()
    detail_box = st.expander("Detalhes técnicos (opcional)", expanded=False)
    steps_box.markdown(
        "<ul class='steps'>"
        "<li><span class='badge wait'>1</span> Upload e salvamento</li>"
        "<li><span class='badge wait'>2</span> Leitura de metadados</li>"
        "<li><span class='badge wait'>3</span> Montando pipeline</li>"
        "<li><span class='badge wait'>4</span> Convertendo vídeo</li>"
        "<li><span class='badge wait'>5</span> Finalizando</li>"
        "</ul>", unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

msg_box = st.empty()
dl_box  = st.empty()

def render_steps(current: int, converting_text: str = ""):
    labels = [
        "Upload e salvamento",
        "Leitura de metadados",
        "Montando pipeline",
        "Convertendo vídeo",
        "Finalizando",
    ]
    html = "<ul class='steps'>"
    for i, label in enumerate(labels, start=1):
        cls = "done" if i <= current else ("run" if i == current + 1 else "wait")
        txt = label
        if i == 4 and converting_text:
            txt += f" — {converting_text}"
        html += f"<li><span class='badge {cls}'>{i}</span> {txt}</li>"
    html += "</ul>"
    steps_box.markdown(html, unsafe_allow_html=True)

# ============== Lógica principal ==============
if convert_btn and file is not None:
    # 1) Upload/Salvar
    render_steps(0)
    tmp_in = Path(tempfile.gettempdir()) / f"in_{next(tempfile._get_candidate_names())}{Path(file.name).suffix or '.mp4'}"
    with open(tmp_in, "wb") as f:
        f.write(file.getbuffer())
    msg_box.info(f"Arquivo salvo: **{tmp_in}**")
    render_steps(1)

    # 2) Metadados
    info = ffprobe_json(tmp_in)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    try:
        duration_s = float(info.get("format", {}).get("duration") or 0.0)
    except Exception:
        duration_s = 0.0
    render_steps(2)

    # 3) Monta pipeline
    out_name = f"{Path(file.name).stem}_android.mp4"
    tmp_out = Path(tempfile.gettempdir()) / f"out_{next(tempfile._get_candidate_names())}.mp4"

    if is_android_friendly(v, a) and max_height == 0 and cfr == 0:
        cmd = ["ffmpeg", "-y", "-i", str(tmp_in), "-c", "copy", "-movflags", "+faststart", str(tmp_out)]
        plan_text = "Compatível detectado → **cópia sem reencode**."
        show_progress = False
    else:
        vf = build_vf(v, max_height)
        cmd = [
            "ffmpeg", "-y", "-i", str(tmp_in),
            "-vf", vf,
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1",
            "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ac", "2",
            "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp_out)
        ]
        if cfr and int(cfr) > 0:
            # insere antes do -movflags
            cmd[-3:-3] = ["-r", str(int(cfr)), "-vsync", "cfr"]
        plan_text, show_progress = "Reencode com H.264 + AAC.", True

    msg_box.info(plan_text)
    render_steps(3)

    progress = prog_box.progress(0, text="Iniciando…")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        if show_progress:
            percent = 0
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                if "out_time_ms=" in line and duration_s > 0:
                    try:
                        out_ms = int(line.strip().split("=")[1])
                        percent = min(100, int(out_ms / (duration_s * 1e6) * 100))
                        progress.progress(percent, text=f"Convertendo… {percent}%")
                        render_steps(3, converting_text=f"{percent}%")
                    except Exception:
                        pass
                elif line.strip().startswith("progress=") and "end" in line:
                    progress.progress(100, text="Finalizando…")
                    render_steps(3, converting_text="100%")
        ret = proc.wait()
        err = proc.stderr.read() if proc.stderr else ""
        if err:
            detail_box.code((err or "")[-3000:])
    except Exception as e:
        ret = -1
        detail_box.code(f"[app] erro ao executar: {e}")

    # 5) Finaliza
    render_steps(4)
    if ret != 0:
        msg_box.error("Falha na conversão. Veja detalhes técnicos (opcional).")
    else:
        msg_box.success("Pronto! Conversão concluída. ✅")
        with open(tmp_out, "rb") as f:
            data = f.read()
        with st.container():
            st.markdown("<div class='center-dl'>", unsafe_allow_html=True)
            dl_box.download_button("⬇️ Baixar convertido", data=data, file_name=out_name, mime="video/mp4")
            st.markdown("</div>", unsafe_allow_html=True)
        if st.toggle("Pré-visualizar aqui", value=False):
            st.video(data)

# ===== Footer (alinhado à direita) =====
st.markdown("""
<div class='footer-right'>
  <div class='footer-card'>
    <div>Prepared By</div>
    <div><b>Reginaldo Sousa</b></div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)  # fecha .frame
