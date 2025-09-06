import streamlit as st
# --- UI ---


st.title("🎬 Conversor de Vídeo (Android/Windows compatível)")
st.write("Converte para **H.264 + AAC**, `yuv420p`, com **faststart**. Detecta **HDR/10-bit** e aplica *tonemap* para SDR quando necessário.")


with st.sidebar:
st.header("Opções")
max_height = st.selectbox("Limitar altura", [0, 720, 1080, 1440, 2160], index=2, format_func=lambda x: "Manter" if x==0 else f"{x}p")
cfr = st.selectbox("Travar FPS (CFR)", [0, 24, 30, 60], index=0, format_func=lambda x: "Não travar" if x==0 else f"{x} fps")
crf = st.slider("Qualidade (CRF)", 18, 26, 20)
preset = st.selectbox("Preset", ["fast", "medium", "slow"], index=1)


file = st.file_uploader("Escolha um vídeo", type=["mp4","mov","m4v","mkv","avi","webm"])


if file is not None:
st.write(f"**Arquivo:** {file.name} — {file.size/1024/1024:.1f} MB")


if st.button("Converter"):
with st.status("Convertendo… aguarde", expanded=True) as status:
# salva upload
tmp_in = Path(tempfile.gettempdir()) / f"in_{next(tempfile._get_candidate_names())}{Path(file.name).suffix or '.mp4'}"
with open(tmp_in, "wb") as f:
f.write(file.getbuffer())
st.write("Arquivo salvo:", tmp_in)


info = ffprobe_json(tmp_in)
v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)


out_name = f"{Path(file.name).stem}_android.mp4"
tmp_out = Path(tempfile.gettempdir()) / f"out_{next(tempfile._get_candidate_names())}.mp4"


# Decisão: copiar ou reencodar
if is_android_friendly(v, a) and max_height == 0 and cfr == 0:
cmd = ["ffmpeg", "-y", "-i", str(tmp_in), "-c", "copy", "-movflags", "+faststart", str(tmp_out)]
st.write("Compatível detectado → copiando sem reencode…")
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
st.code(p.stderr[-4000:])
status.update(label="Erro", state="error")
else:
st.success("Pronto!")
with open(tmp_out, "rb") as f:
data = f.read()
st.download_button("⬇️ Baixar convertido", data=data, file_name=out_name, mime="video/mp4")
st.video(data)
status.update(label="Concluído", state="complete")
