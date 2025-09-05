# streamlit_app.py
import streamlit as st
import subprocess, json, tempfile
from pathlib import Path
from typing import Optional

st.set_page_config(page_title="Conversor de Vídeo (Android/Windows)", page_icon="🎬", layout="centered")

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

    # HDR/10-bit → tenta tonemap; se não tiver zscale, faz fallback
    if needs_tonemap(v):
        if HAS_ZSCALE:
            # Tonemap correto (libzimg/zscale)
            filters.append("zscale=t=linear:npl=100,tonemap=hable:desat=0,"
                           "zscale=matrix=bt709:transfer=bt709:primaries=bt709")
        else:
            # Fallback sem zscale: converte espaço de cor pra bt709 (resolve bem p/ marketing/social)
            filters.append("colorspace=all=bt709:fast=1")

    # Redimensiona mantendo proporção
    if max_h and max_h > 0:
        # precisa escapar a vírgula na expressão
        filters.append(f"scale=-2:min(ih\\,{max_h}):flags=bicubic")

    # Garantir compatibilidade Android/Windows
    filters.append("format=yuv420p")
    return ",".join(filters)

# -----------------------
# UI
# -----------------------
st.title("🎬 Conversor de Vídeo (Android/Windows compatível)")
st.write(
    "Converte para **H.264 + AAC**, `yuv420p`, com **faststart**. "
    "Detecta **HDR/10-bit** e aplica *tonemap* para SDR quando possível."
)
with st.sidebar:
    st.header("Opções")
    max_height = st.selectbox("Limitar altura", [0, 720, 1080, 1440, 2160],
                              index=2, format_func=lambda x: "Manter" if x==0 else f"{x}p")
    cfr = st.selectbox("Travar FPS (CFR)", [0, 24, 30, 60],
                       index=0, format_func=lambda x: "Não travar" if x==0 else f"{x} fps")
    crf = st.slider("Qualidade (CRF)", 18, 26, 20)
    preset = st.selectbox("Preset", ["fast", "medium", "slow"], index=1)

file = st.file_uploader("Escolha um vídeo", type=["mp4","mov","m4v","mkv","avi","webm"])

if file is not None:
    st.write(f"**Arquivo:** {file.name} — {file.size/1024/1024:.1f} MB")
    if HAS_ZSCALE:
        st.caption("Filtro **zscale** disponível ✅ (tonemap HDR→SDR completo).")
    else:
        st.caption("Filtro **zscale** indisponível ⚠️ usando fallback `colorspace` (boa compatibilidade).")

    if st.button("Converter"):
        with st.status("Convertendo… aguarde", expanded=True) as status:
            # Salva upload para /tmp
            tmp_in = Path(tempfile.gettempdir()) / f"in_{next(tempfile._get_candidate_names())}{Path(file.name).suffix or '.mp4'}"
            with open(tmp_in, "wb") as f:
                f.write(file.getbuffer())
            st.write("Arquivo salvo:", tmp_in)

            # Inspeciona
            info = ffprobe_json(tmp_in)
            v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
            a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)

            out_name = f"{Path(file.name).stem}_android.mp4"
            tmp_out = Path(tempfile.gettempdir()) / f"out_{next(tempfile._get_candidate_names())}.mp4"

            # Copiar ou reencodar?
            if is_android_friendly(v, a) and max_height == 0 and cfr == 0:
                cmd = ["ffmpeg", "-y", "-i", str(tmp_in), "-c", "copy", "-movflags", "+faststart", str(tmp_out)]
                st.write("Compatível detectado → **cópia sem reencode**.")
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
                st.write("Comando ffmpeg:", " ".join(cmd))

            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                st.error("Falha na conversão.")
                # mostra só o final do log para não poluir
                st.code(p.stderr[-4000:])
                status.update(label="Erro", state="error")
            else:
                st.success("Pronto!")
                with open(tmp_out, "rb") as f:
                    data = f.read()
                st.download_button("⬇️ Baixar convertido", data=data, file_name=out_name, mime="video/mp4")
                st.video(data)
                status.update(label="Concluído", state="complete")
