FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip espeak-ng curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Node app deps
WORKDIR /app
COPY server/package.json .
RUN npm install --production
COPY server/ .

# Installed as two separate steps so pip resolves each independently,
# instead of backtracking argostranslate into an old version that pulls in
# the PyQt5 GUI toolkit (which needs a Qt build toolchain we don't have and
# don't need for command-line translation).
RUN pip3 install --break-system-packages --no-cache-dir "argostranslate>=1.9,<2"
RUN pip3 install --break-system-packages --no-cache-dir piper-tts

# Install the Persian -> English Argos Translate model at build time
RUN python3 -c "\
import argostranslate.package as pkg; \
pkg.update_package_index(); \
avail = pkg.get_available_packages(); \
match = next(p for p in avail if p.from_code == 'fa' and p.to_code == 'en'); \
pkg.install_from_path(match.download())"

# Warm up the translation pipeline once at build time. The Persian model
# depends on an extra tokenizer component ("mwt") from the Stanza library
# that downloads over the network the first time it's used -- doing that
# now bakes it into the image instead of stalling the first real request.
RUN python3 -c "\
import argostranslate.translate as translate; \
langs = translate.get_installed_languages(); \
fa = next(l for l in langs if l.code == 'fa'); \
en = next(l for l in langs if l.code == 'en'); \
t = fa.get_translation(en); \
print('warm-up translation:', t.translate('سلام'))"

# Download a community Persian voice model for Piper.
# Check https://huggingface.co/rhasspy/piper-voices/tree/main/fa/fa_IR for the
# current filename if this path ever changes.
RUN mkdir -p /app/models && \
    curl -L -o /app/models/fa_IR-gyro-medium.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/fa/fa_IR/gyro/medium/fa_IR-gyro-medium.onnx" && \
    curl -L -o /app/models/fa_IR-gyro-medium.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/fa/fa_IR/gyro/medium/fa_IR-gyro-medium.onnx.json"

EXPOSE 8099

CMD ["node", "server.js"]
