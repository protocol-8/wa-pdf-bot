#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing LibreOffice and fonts..."
apt-get update && apt-get install -y \
  libreoffice \
  libreoffice-writer \
  libreoffice-impress \
  default-jre \
  fonts-noto \
  fonts-noto-core \
  fonts-noto-extra \
  fonts-indic \
  fonts-deva \
  fonts-lohit-deva \
  fonts-samyak-deva \
  git \
  fontconfig

echo "==> Installing Kruti Dev fonts..."
mkdir -p /usr/share/fonts/truetype/krutidev
git clone --depth=1 https://github.com/Narenbairagi11/krutidev /tmp/krutidev
cp /tmp/krutidev/*.TTF /usr/share/fonts/truetype/krutidev/ || true
cp /tmp/krutidev/*.ttf /usr/share/fonts/truetype/krutidev/ || true
fc-cache -f -v

echo "==> Build complete!"
