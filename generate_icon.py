"""
Генератор полноценного мультиразмерного app_icon.ico для CatKeyboardBlocker.exe
"""
from PIL import Image, ImageDraw

def create_high_res_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    bg_color = "#2C3E50"
    keyboard_body = "#00B894"
    keyboard_border = "#019875"
    key_color = "#00A381"
    key_active = "#55EFC4"
    cat_ear_color = "#E17055"
    cat_inner_ear = "#FAB1A0"
    badge_color = "#E74C3C"

    # 1. Тень и подложка
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=50, fill=bg_color, outline="#1A252F", width=6)

    # 2. Кошачьи ушки над клавиатурой
    d.polygon([(46, 96), (70, 36), (106, 88)], fill=cat_ear_color, outline="#D63031")
    d.polygon([(56, 90), (72, 50), (96, 84)], fill=cat_inner_ear)
    d.polygon([(size - 46, 96), (size - 70, 36), (size - 106, 88)], fill=cat_ear_color, outline="#D63031")
    d.polygon([(size - 56, 90), (size - 72, 50), (size - 96, 84)], fill=cat_inner_ear)

    # 3. Корпус клавиатуры
    kx1, ky1, kx2, ky2 = 28, 76, size - 28, size - 32
    d.rounded_rectangle([kx1, ky1, kx2, ky2], radius=24, fill=keyboard_body, outline=keyboard_border, width=8)

    # 4. Клавиши
    rows = [
        (ky1 + 20, 10, 24),
        (ky1 + 54, 9, 24),
        (ky1 + 88, 8, 24),
    ]
    total_w = (kx2 - kx1) - 36
    start_x = kx1 + 18

    for ry, count, kh in rows:
        gap = 4
        kw = (total_w - gap * (count - 1)) / count
        for i in range(count):
            x1 = start_x + i * (kw + gap)
            kc = key_active if (i in (1, 3, 5) and ry == rows[0][0]) else key_color
            d.rounded_rectangle([x1, ry, x1 + kw, ry + kh], radius=6, fill=kc)

    # Пробел
    sp_y = ky1 + 122
    sp_w = total_w * 0.55
    sp_x = start_x + (total_w - sp_w) / 2
    d.rounded_rectangle([sp_x, sp_y, sp_x + sp_w, sp_y + 20], radius=7, fill=key_active)

    # 5. Кошачья лапка поверх правого угла
    paw_x, paw_y = size - 70, size - 74
    d.ellipse([paw_x - 14, paw_y - 12, paw_x + 14, paw_y + 12], fill="#FFFFFF", outline="#DFE6E9", width=2)
    toes = [(-16, -18), (-6, -26), (6, -26), (16, -18)]
    for tx, ty in toes:
        d.ellipse([paw_x + tx - 5, paw_y + ty - 6, paw_x + tx + 5, paw_y + ty + 6], fill="#FFFFFF")

    # Розовые подушечки
    d.ellipse([paw_x - 8, paw_y - 6, paw_x + 8, paw_y + 8], fill="#FAB1A0")
    for tx, ty in toes:
        d.ellipse([paw_x + tx - 3, paw_y + ty - 3, paw_x + tx + 3, paw_y + ty + 3], fill="#FAB1A0")

    # 6. Бэйджик-замок сверху
    d.ellipse([size - 52, 20, size - 16, 56], fill=badge_color, outline="white", width=4)
    d.arc([size - 42, 28, size - 26, 44], start=180, end=0, fill="white", width=3)
    d.rectangle([size - 40, 36, size - 28, 48], fill="white")

    return img

def main():
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    base_img = create_high_res_icon(512)
    
    # В Pillow для ICO список размеров передается в параметре sizes у исходного большого изображения:
    base_img.save("app_icon.ico", format="ICO", sizes=sizes)
    print("Полноценный мультиразмерный app_icon.ico успешно сохранен!")

if __name__ == "__main__":
    main()
