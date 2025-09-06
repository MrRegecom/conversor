# streamlit_app.py
import streamlit as st
import subprocess, json, tempfile, time
from pathlib import Path
from typing import Optional

st.set_page_config(
    page_title="Conversor de Vídeo (Android/Windows)",
    page_icon="🎬",
    layout="wide",
)

# =========================
# Estilos (frame + steps)
# =========================
st.markdown("""
<style>
.block-container {max-width: 1200px; padding-top: 1.0rem;}
.frame {
  border: 1px solid rgba(120,120,120,.35);
  border-radius: 16px;
  padding: 18px 20px;
  box-shadow: 0 10px 25px rgba(0,0,0,.10);
  background: rgba(255,255,255,.02);
}
.side-card {
  border: 1px solid rgba(120,120,120,.25);
  border-radius: 12px;
  padding: 14px 14px 10px;
  background: rgba(255,255,255,.03);
}
.steps {list-style:none; margin: 0; padding: 0;}
.steps li {margin: 6px 0; display:flex; gap:8px; align-items:center;}
.badge {
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%;
  font-size:.85rem; font-weight:700; color:#fff;
}
.badge.wait {background:#666;}
.badge.run  {background:#915eff;}
.badge.done {background:#2aa84a;}
.center-dl {display:flex; justify-content:center; margin: 14px 0 6px;}
.footer {text-align:center; margin-top:18px; opacity:.7;}
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# =========================
# Helpers / FFmpeg
# =========================
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

# =========================
# Decisão
# =========================
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
            # Fallback sem zscale: mapeia cores para BT.709 (boa compatibilidade)
            filters.append("colorspace=all=bt709:fast=1")
    if max_h and max_h > 0:
        filters.append(f"scale=-2:min(ih\\,{max_h}):flags=bicubic")
    filters.append("format=yuv420p")
    return ",".join(filters)

# =========================
# UI
# =========================
st.markdown("<div class='frame'>", unsafe_allow_html=True)
st.markdown("## 🎬 Conversor de Vídeo (Android/Windows compatível)")
st.caption(
    "Converte para **H.264 + AAC**, `yuv420p`, com **faststart**. "
    "Detecta **HDR/10-bit** e aplica *tonemap* para SDR quando possível."
)

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

    convert_btn = st.button("Converter", use_container_width=True)

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
    """current: 0..5 (quantas etapas já concluídas)."""
    html = "<ul class='steps'>"
    labels = [
        "Upload e salvamento",
        "Leitura de metadados",
        "Montando pipeline",
        "Convertendo vídeo",
        "Finalizando",
    ]
    for i, label in enumerate(labels, start=1):
        cls = "done" if i <= current else ("run" if i == current + 1 else "wait")
        txt = label
        if i == 4 and converting_text:
            txt += f" — {converting_text}"
        html += f"<li><span class='badge {cls}'>{i}</span> {txt}</li>"
    html += "</ul>"
    steps_box.markdown(html, unsafe_allow_html=True)

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
    duration_s = 0.0
    try:
        duration_s = float(info.get("format", {}).get("duration") or 0.0)
    except Exception:
        duration_s = 0.0
    render_steps(2)

    # 3) Montando pipeline
    out_name = f"{Path(file.name).stem}_android.mp4"
    tmp_out = Path(tempfile.gettempdir()) / f"out_{next(tempfile._get_candidate_names())}.mp4"

    if is_android_friendly(v, a) and max_height == 0 and cfr == 0:
        cmd = ["ffmpeg", "-y", "-i", str(tmp_in), "-c", "copy", "-movflags", "+faststart", str(tmp_out)]
        plan_text = "Compatível detectado → **cópia sem reencode**."
    else:
        vf = build_vf(v, max_height)
        cmd = [
            "ffmpeg", "-y", "-i", str(tmp_in),
            "-vf", vf,
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1",
            "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ac", "2",
        ]
        if cfr and int(cfr) > 0:
            cmd += ["-r", str(int(cfr)), "-vsync", "cfr"]
        cmd += ["-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats",  # habilita progresso parsável
                str(tmp_out)]
        plan_text = "Reencode com H.264 + AAC."
    msg_box.info(plan_text)
    render_steps(3)

    # 4) Converter com barra de progresso
    progress = prog_box.progress(0, text="Iniciando conversão…")
    out_lines = []
    percent = 0
    try:
        # Quando passamos -progress pipe:1, o FFmpeg imprime linhas key=value no STDOUT
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            out_lines.append(line)
            if "out_time_ms=" in line and duration_s > 0:
                try:
                    out_ms = int(line.strip().split("=")[1])
                    percent = min(100, int(out_ms / (duration_s * 1e6) * 100))
                    progress.progress(percent, text=f"Convertendo… {percent}%")
                    render_steps(3, converting_text=f"{percent}%")
                except Exception:
                    pass
            elif line.strip().startswith("progress=") and "end" in line:
                percent = 100
                progress.progress(percent, text="Finalizando…")
                render_steps(3, converting_text="100%")
        ret = proc.wait()
        # guardar stderr (apenas se precisar ver na aba de detalhes)
        err = proc.stderr.read() if proc.stderr else ""
        if err:
            detail_box.code((err or "")[-3000:])
    except Exception as e:
        ret = -1
        detail_box.code(f"[app] erro ao executar: {e}")

    # 5) Finalizar
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
        if st.session_state.get("preview_on", None) is None:
            st.session_state["preview_on"] = show_preview
        if show_preview:
            st.video(data)

st.markdown("<div class='footer'>prepared by <b>Reginaldo Sousa</b></div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)  # fecha .frame
