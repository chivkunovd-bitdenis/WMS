from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/pdf/vms-release-2026-10-07.pdf"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
pdfmetrics.registerFont(TTFont("Arial", FONT))
pdfmetrics.registerFont(TTFont("Arial-Bold", BOLD))

ITEMS = [
    ("Массовый подбор WB", "Собирайте несколько поставок за один обход: система сведёт количества и покажет места хранения."),
    ("Сохранённые сборки", "Сборка получает номер и показывает прогресс - экран можно закрыть и позже продолжить."),
    ("Общая упаковка", "Упаковывайте товары разных поставок в одном окне: скан сам найдёт подходящий заказ."),
    ("Печать по сканированию", "Отсканируйте товар и, если нужно, маркировку - этикетка уйдёт на принтер через WMS Print для Windows или Mac."),
    ("Какие этикетки печатать", "Выберите QR-код заказа WB, новый код «Честного знака» из загруженных или копию скана и укажите число экземпляров."),
    ("Отмена шага упаковки", "Отмените последнее действие и продолжайте упаковку с этого места."),
    ("Замена маркировки", "Отсканируйте новый код прямо в строке нужного заказа."),
    ("Только отклонённые коды", "Покажите заказы с маркировкой, которую отклонила WB."),
    ("Замечания к отгрузке", "Смотрите замечания по причинам и раскрывайте список конкретных заказов."),
    ("Синхронизация Ozon и WB", "Сдача созданных в системе поставок через кабинет площадки обновляет статусы, остатки и резервы; частичная сдача учитывает подтверждённые позиции."),
    ("Таможенные данные Ozon", "Укажите в заказе отсутствие таможенных документов и передайте отметку в Ozon."),
    ("Общий лист подбора", "Распечатайте один список на несколько поставок с общими количествами и ячейками."),
    ("Короб и источник товара", "В листе видны приёмка или возврат, текущая ячейка, короб и количество - товар проще найти."),
    ("Заказы в кабинете продавца", "Просматривайте свои FBS-заказы, их статусы, количества, дату и время с момента поступления."),
    ("Фильтры товаров продавца", "Отбирайте товары по площадке, артикулу, размеру и наличию, группируйте по категории, артикулу или размеру."),
    ("Товары с остатком", "Оставьте в списке позиции, которые физически находятся на складе."),
    ("Настройка остатков", "Откройте настройки продаж для выбранных товаров прямо из приёмки или возврата."),
    ("Приёмка из Excel", "Загрузите товары и количества из файла; система проверит строки до внесения изменений."),
    ("Адреса ячеек под склад", "Настройте стороны и ярусы и заранее посмотрите, как будет выглядеть адрес ячейки."),
    ("Наглядное размещение", "Видно, что ещё нужно разложить и что уже стоит в ячейках; последнее перемещение можно отменить."),
    ("Короба на всю партию", "Создайте нужное число коробов одной командой при приёмке или возврате."),
    ("Печать всех этикеток коробов", "Печатайте весь комплект этикеток одной командой."),
    ("Понятные этикетки коробов", "На этикетке указаны номер и дата приёмки, а также продавец."),
    ("Размер и цвет в формах", "Размер и цвет варианта товара помогают различать похожие позиции на печатных формах."),
    ("Сборка на терминале", "Подбирайте заказы на терминале: фото и места хранения под рукой, доступны ручной ввод, отмена и продолжение сборки."),
    ("Приёмка на терминале", "Открывайте и закрывайте короб и принимайте товары на одном экране; план и уже принятое количество видны сразу."),
    ("Проданные коды WB", "Сверяйте фактические продажи с возвратами по периоду, товару, цене и статусу и готовьте коды к выводу из оборота."),
]

NAVY = colors.HexColor("#142B45")
TEAL = colors.HexColor("#12A89D")
MUTED = colors.HexColor("#68798A")
RULE = colors.HexColor("#DFE7EB")
PALE = colors.HexColor("#EAF7F6")

BODY = ParagraphStyle("body", fontName="Arial", fontSize=9.5, leading=13.1, textColor=NAVY)
TITLE = ParagraphStyle("title", fontName="Arial-Bold", fontSize=12, leading=14, textColor=NAVY)


def icon(c, x, y, index):
    c.saveState()
    c.setFillColor(PALE)
    c.circle(x + 13, y - 13, 13, fill=1, stroke=0)
    c.setStrokeColor(TEAL)
    c.setFillColor(colors.white)
    c.setLineWidth(1.5)
    if index in (4, 5, 7, 27):  # barcode / scan
        for i, h in enumerate((8, 12, 6, 10, 13, 7, 11)):
            c.setLineWidth(1 if i % 2 else 1.7)
            c.line(x + 8 + i * 1.6, y - 19, x + 8 + i * 1.6, y - 19 + h)
    elif index in (9, 10):  # sync
        c.arc(x + 7, y - 20, x + 20, y - 7, 35, 230)
        c.arc(x + 6, y - 20, x + 19, y - 7, 215, 230)
        c.line(x + 17, y - 9, x + 20, y - 10)
        c.line(x + 17, y - 9, x + 17, y - 12)
    elif index in (14, 17, 18, 22, 23, 24):  # document / print
        c.roundRect(x + 7, y - 19, 12, 12, 2, fill=0, stroke=1)
        c.line(x + 10, y - 10, x + 16, y - 10)
        c.line(x + 10, y - 13, x + 16, y - 13)
        c.line(x + 10, y - 16, x + 14, y - 16)
    elif index in (19, 20, 21):  # storage cells / boxes
        c.rect(x + 7, y - 19, 12, 12, fill=0, stroke=1)
        c.line(x + 13, y - 19, x + 13, y - 7)
        c.line(x + 7, y - 13, x + 19, y - 13)
    elif index in (25, 26):  # mobile terminal
        c.roundRect(x + 9, y - 20, 8, 14, 2, fill=0, stroke=1)
        c.circle(x + 13, y - 17.5, 0.7, fill=1, stroke=0)
    elif index in (8, 15, 16):  # filter
        c.line(x + 7, y - 8, x + 19, y - 8)
        c.line(x + 9, y - 8, x + 12, y - 13)
        c.line(x + 17, y - 8, x + 14, y - 13)
        c.line(x + 12, y - 13, x + 12, y - 18)
        c.line(x + 14, y - 13, x + 14, y - 18)
    elif index in (3, 6):  # printer / packing action
        c.roundRect(x + 7, y - 16, 12, 8, 2, fill=0, stroke=1)
        c.rect(x + 9, y - 20, 8, 5, fill=0, stroke=1)
        c.line(x + 10, y - 11, x + 16, y - 11)
    elif index in (1, 2, 11, 12, 13):  # warehouse / picking list
        c.rect(x + 7, y - 19, 12, 12, fill=0, stroke=1)
        c.line(x + 9, y - 13, x + 17, y - 13)
        c.line(x + 9, y - 16, x + 17, y - 16)
    else:
        c.circle(x + 13, y - 13, 6, fill=0, stroke=1)
        c.line(x + 13, y - 13, x + 13, y - 9)
        c.line(x + 13, y - 13, x + 16, y - 15)
    c.restoreState()


def draw_item(c, item, idx, x, top, width):
    title, desc = item
    icon(c, x, top, idx)
    tx = x + 36
    titlep = Paragraph(f'<font color="#12A89D">{idx:02d}</font>  {title}', TITLE)
    _, th = titlep.wrap(width - 40, 32)
    titlep.drawOn(c, tx, top - th + 1)
    p = Paragraph(desc, BODY)
    _, ph = p.wrap(width - 40, 52)
    p.drawOn(c, tx, top - th - 5 - ph)
    bottom = top - th - 12 - ph
    c.setStrokeColor(RULE)
    c.setLineWidth(0.55)
    c.line(tx, bottom - 8, x + width, bottom - 8)
    return bottom - 21


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=A4)
    c.setTitle("VMS · Обновления · 07.10.2026")
    c.setAuthor("VMS")
    W, H = A4
    margin = 42
    gap = 24
    colw = (W - 2 * margin - gap) / 2
    groups = [ITEMS[:14], ITEMS[14:]]
    idx = 1
    for page, group in enumerate(groups, 1):
        c.setFillColor(TEAL)
        c.roundRect(margin, H - 54, 5, 27, 2, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("Arial-Bold", 23)
        c.drawString(margin + 15, H - 45, "VMS · Обновления")
        c.setFillColor(MUTED)
        c.setFont("Arial", 10)
        c.drawRightString(W - margin, H - 39, "07.10.2026")
        c.setStrokeColor(RULE)
        c.line(margin, H - 70, W - margin, H - 70)
        # Evenly split each page into balanced columns.
        left_count = (len(group) + 1) // 2
        for column, subset in enumerate((group[:left_count], group[left_count:])):
            x = margin + column * (colw + gap)
            top = H - 96
            for item in subset:
                top = draw_item(c, item, idx, x, top, colw)
                idx += 1
        c.setStrokeColor(RULE)
        c.line(margin, 35, W - margin, 35)
        c.setFillColor(MUTED)
        c.setFont("Arial", 8.5)
        c.drawString(margin, 21, "Возможности системы")
        c.drawRightString(W - margin, 21, f"{page:02d} / 02")
        c.showPage()
    c.save()


if __name__ == "__main__":
    main()
