#!/bin/bash

# ERPNext AI - GitHub ga push qilish scripti

cd "$(dirname "$0")"

echo "==> Git status tekshirilmoqda..."
git status

echo ""
echo "==> GitHub ga push qilinmoqda..."
echo "Agar parol so'ralsa, GitHub username va password/token kiriting"

git push origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Muvaffaqiyatli push qilindi!"
    echo "Repository: https://github.com/WIKKIwk/erpnext_ai"
else
    echo ""
    echo "❌ Push xatosi yuz berdi"
    echo ""
    echo "Quyidagi buyruqni terminal da ishga tushiring:"
    echo "  cd /home/victus/Downloads/erpnext_bundle/my-bench/apps/erpnext_ai"
    echo "  git push origin main"
fi
