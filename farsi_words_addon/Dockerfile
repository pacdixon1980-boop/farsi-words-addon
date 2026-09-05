FROM node:20-alpine

RUN apk add --no-cache python3 py3-pip espeak-ng curl ffmpeg

# Node app deps
WORKDIR /app
COPY server/package.json .
RUN npm install --production
COPY server/ .

# Python deps for offline translation (Argos Translate)
RUN pip3 install --break-system-packages --no-cache-dir argostranslate piper-tts

# Install the Persian -> English Argos Translate model at build time
RUN python3 -c "\
import argostranslate.package as pkg; \
pkg.update_package_index(); \
avail = pkg.get_available_packages(); \
match = next(p for p in avail if p.from_code == 'fa' and p.to_code == 'en'); \
pkg.install_from_path(match.download())"

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
