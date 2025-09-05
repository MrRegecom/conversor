# streamlit_app.py
import streamlit as st
import subprocess, json, tempfile, time
from pathlib import Path
from typing import Optional

st.set_page_config(
    page_title="Conversor de Vídeo (Android/Windows)",
    page_icon="🎬",
    layout="wide"
)

# -----------------------
# Estilos (frame + centralização + rodapé)
# -----------------------
st.markdown("""
<style>
/* Largura máxima e “moldura” do app */
.block-container {max-width: 1200px; padding-top: 1.25rem;}
.frame {
  border: 1px solid rgba(120,120,120,.35);
  border-radius: 16px;
  padding: 18px 20px;
  box-shadow: 0 10px 25px rgba(0,0,0,.10);
  background: rgba(255,255,255,.02);
}
/* Painel de logs com altura fixa */
.log-card {
  border: 1px solid rgba(120,120,120,.25);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255,255,255,.03);
}
.center-dl {display:flex; justify-content:center; margin: 14px 0 6px;}
.small {opacity:.75; font-size:.9rem;}
.footer {text-align:center; margin-top:18px; opacity:.7;}
/* Esconde o footer nativo do Streamlit */
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------------
# Helpers de sistema/ffmpeg
# -----------------------
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

# -----------------------
# Lógica de decisão
# -----------------------
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
            # Tonemap correto (libzimg/zscale)
            filters.append("zscale=t=linear:npl=100,tonemap=hable:desat=0,"
                           "zscale=matrix=bt709:transfer=bt709:primaries=bt709")
        else:
            # Fallback sem zscale: converte cores para bt709 (boa compatibilidade)
            filters.append("colorspace=all=bt709:fast=1")

    if max_h and max_h > 0:
        filters.append(f"scale=-2:min(ih\\,{max_h}):flags=bicubic")

    filters.append("format=yuv420p")
    return ",".join(filters)

# -----------------------
# UI
# -----------------------
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
    c1, c2 = st.columns(2)
    with c1:
        max_height = st.selectbox("Limitar altura", [0, 720, 1080, 1440, 2160],
                                  index=2, format_func=lambda x: "Manter" if x==0 else f"{x}p")
        preset = st.selectbox("Preset", ["fast", "medium", "slow"], index=1)
    with c2:
        cfr = st.selectbox("Travar FPS (CFR)", [0, 24, 30, 60],
                           index=0, format_func=lambda x: "Não travar" if x==0 else f"{x} fps")
        crf = st.slider("Qualidade (CRF)", 18, 26, 20)

    show_preview = st.toggle("Mostrar preview do convertido (pode aumentar o uso de memória)", value=False)
    if HAS_ZSCALE:
        st.caption("Filtro **zscale** disponível ✅ (tonemap HDR→SDR completo).")
    else:
        st.caption("Filtro **zscale** indisponível ⚠️ — usando fallback `colorspace` (boa compatibilidade).")

    convert_btn = st.button("Converter", use_container_width=True)

with right:
    st.markdown("#### Logs de conversão")
    st.markdown("<div class='log-card'>", unsafe_allow_html=True)
    logs_box = st.empty()  # mantemos o painel sempre no mesmo lugar
    # altura fixa via text_area evita rolagem da página
    logs_box.text_area("",
        value="Aguardando arquivo...",
        height=420, label_visibility="collapsed"
    )
    st.markdown("</div>", unsafe_allow_html=True)

# Espaços para mensagens e download centralizado
msg_box = st.empty()
dl_box = st.empty()

if convert_btn and file is not None:
    # Salva upload
    tmp_in = Path(tempfile.gettempdir()) / f"in_{next(tempfile._get_candidate_names())}{Path(file.name).suffix or '.mp4'}"
    with open(tmp_in, "wb") as f:
        f.write(file.getbuffer())

    info = ffprobe_json(tmp_in)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)

    out_name = f"{Path(file.name).stem}_android.mp4"
    tmp_out = Path(tempfile.gettempdir()) / f"out_{next(tempfile._get_candidate_names())}.mp4"

    if is_android_friendly(v, a) and max_height == 0 and cfr == 0:
        cmd = ["ffmpeg", "-y", "-i", str(tmp_in), "-c", "copy", "-movflags", "+faststart", str(tmp_out)]
        cmd_label = "Compatível detectado → **cópia sem reencode**."
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
        cmd += ["-movflags", "+faststart", str(tmp_out)]
        cmd_label = "Executando reencode…"

    msg_box.info(f"Arquivo salvo: **{tmp_in}**\n\n{cmd_label}")

    # Executa ffmpeg com LOG vivo dentro do painel fixo
    buffer = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # lê stderr em “tempo real”
        for line in proc.stderr:
            line = line.rstrip("\n")
            buffer.append(line)
            # mantém só o final para não crescer demais
            if len(buffer) > 400:
                buffer = buffer[-400:]
            logs_box.text_area("", value="\n".join(buffer), height=420, label_visibility="collapsed")
        ret = proc.wait()
    except Exception as e:
        ret = -1
        buffer.append(f"[app] erro ao executar: {e}")
        logs_box.text_area("", value="\n".join(buffer), height=420, label_visibility="collapsed")

    if ret != 0:
        msg_box.error("Falha na conversão. Veja os logs ao lado.")
    else:
        msg_box.success("Pronto! Conversão concluída. ✅")
        with open(tmp_out, "rb") as f:
            data = f.read()
        # Botão de download CENTRALIZADO
        with st.container():
            st.markdown("<div class='center-dl'>", unsafe_allow_html=True)
            dl_box.download_button("⬇️ Baixar convertido", data=data, file_name=out_name, mime="video/mp4")
            st.markdown("</div>", unsafe_allow_html=True)
        if show_preview:
            st.video(data)

# Rodapé
st.markdown("<div class='footer'>prepared by <b>Reginaldo Sousa</b></div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)  # fecha .frame
