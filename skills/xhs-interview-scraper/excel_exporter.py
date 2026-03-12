"""
Excel Exporter Module
Excel 导出模块 - 将抓取到的面试笔记结构化存储到 Excel

支持功能：
- 创建新的Excel文件
- 追加数据到现有Excel文件（增量更新）
- 按公司/时间/方向分Sheet存储
- 自动列宽调整
- 条件格式高亮
"""

import logging
import os
from datetime import datetime
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config import DATA_DIR, EXCEL_HEADERS, OUTPUT_EXCEL

logger = logging.getLogger(__name__)

# 表头样式
HEADER_FONT = Font(name="Microsoft YaHei", bold=True, size=11, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
HEADER_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# 数据单元格样式
DATA_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
DATA_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# 高亮样式（高互动笔记）
HIGHLIGHT_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

# 列宽配置
COLUMN_WIDTHS = {
    "笔记ID": 18,
    "标题": 35,
    "内容摘要": 50,
    "发布时间": 20,
    "公司": 18,
    "岗位方向": 20,
    "面试类型": 15,
    "作者昵称": 15,
    "作者ID": 18,
    "作者主页": 35,
    "笔记链接": 40,
    "点赞数": 10,
    "收藏数": 10,
    "评论数": 10,
    "分享数": 10,
    "笔记类型": 10,
    "标签": 30,
    "抓取时间": 20,
    "搜索关键词": 25,
}


def create_workbook() -> Workbook:
    """创建新的工作簿并设置表头"""
    wb = Workbook()
    ws = wb.active
    ws.title = "全部笔记"

    # 写入表头
    for col_idx, header in enumerate(EXCEL_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = HEADER_BORDER

    # 设置列宽
    for col_idx, header in enumerate(EXCEL_HEADERS, 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = COLUMN_WIDTHS.get(header, 15)

    # 冻结首行
    ws.freeze_panes = "A2"

    # 设置筛选
    ws.auto_filter.ref = f"A1:{get_column_letter(len(EXCEL_HEADERS))}1"

    return wb


def add_notes_to_sheet(ws, notes: list[dict], start_row: int = 2):
    """
    将笔记数据写入工作表。

    :param ws: 工作表对象
    :param notes: 笔记数据列表
    :param start_row: 开始写入的行号
    """
    for row_idx, note in enumerate(notes, start_row):
        for col_idx, header in enumerate(EXCEL_HEADERS, 1):
            value = note.get(header, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = DATA_ALIGNMENT
            cell.border = DATA_BORDER

            # 高亮高互动笔记（点赞>100）
            likes = note.get("点赞数", 0)
            if isinstance(likes, int) and likes > 100:
                cell.fill = HIGHLIGHT_FILL


def create_company_sheets(wb: Workbook, notes: list[dict]):
    """
    按公司创建分Sheet，方便按公司查看面试信息。

    :param wb: 工作簿对象
    :param notes: 所有笔记数据
    """
    # 按公司分组
    company_groups: dict[str, list[dict]] = {}
    for note in notes:
        companies = note.get("公司", "未分类")
        if not companies:
            companies = "未分类"
        # 取第一个公司作为分组依据
        primary_company = companies.split(",")[0].strip()
        if primary_company not in company_groups:
            company_groups[primary_company] = []
        company_groups[primary_company].append(note)

    # 为每个公司创建Sheet
    for company, company_notes in sorted(company_groups.items()):
        if len(company_notes) < 2:
            continue  # 跳过笔记太少的公司

        # Excel Sheet名称限制31个字符，且不能包含 \ / * ? : [ ]
        sheet_name = company
        for ch in r'\/*?:[]':
            sheet_name = sheet_name.replace(ch, '_')
        sheet_name = sheet_name[:31]
        # 确保不重名
        if sheet_name in wb.sheetnames:
            sheet_name = f"{sheet_name[:28]}_{len(wb.sheetnames)}"

        ws = wb.create_sheet(title=sheet_name)

        # 写入表头
        for col_idx, header in enumerate(EXCEL_HEADERS, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = HEADER_BORDER

        # 设置列宽
        for col_idx, header in enumerate(EXCEL_HEADERS, 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = COLUMN_WIDTHS.get(header, 15)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(EXCEL_HEADERS))}1"

        # 按点赞数降序排列
        sorted_notes = sorted(
            company_notes,
            key=lambda x: x.get("点赞数", 0) if isinstance(x.get("点赞数", 0), int) else 0,
            reverse=True,
        )
        add_notes_to_sheet(ws, sorted_notes)

    sheets_created = sum(1 for notes in company_groups.values() if len(notes) >= 2)
    logger.info(f"创建了 {sheets_created} 个公司分Sheet")


def create_summary_sheet(wb: Workbook, notes: list[dict]):
    """
    创建统计摘要Sheet。

    :param wb: 工作簿对象
    :param notes: 所有笔记数据
    """
    ws = wb.create_sheet(title="统计摘要", index=0)

    # 标题
    title_font = Font(name="Microsoft YaHei", bold=True, size=14)
    ws.cell(row=1, column=1, value="小红书面试信息抓取统计").font = title_font
    ws.cell(row=2, column=1, value=f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 总计统计
    row = 4
    section_font = Font(name="Microsoft YaHei", bold=True, size=12, color="4472C4")
    ws.cell(row=row, column=1, value="一、总体统计").font = section_font
    row += 1
    ws.cell(row=row, column=1, value="笔记总数")
    ws.cell(row=row, column=2, value=len(notes))
    row += 1

    # 按公司统计
    row += 1
    ws.cell(row=row, column=1, value="二、按公司统计").font = section_font
    row += 1
    ws.cell(row=row, column=1, value="公司").font = Font(bold=True)
    ws.cell(row=row, column=2, value="笔记数").font = Font(bold=True)
    ws.cell(row=row, column=3, value="平均点赞").font = Font(bold=True)
    row += 1

    company_stats: dict[str, dict] = {}
    for note in notes:
        companies = note.get("公司", "未分类") or "未分类"
        primary = companies.split(",")[0].strip()
        if primary not in company_stats:
            company_stats[primary] = {"count": 0, "total_likes": 0}
        company_stats[primary]["count"] += 1
        likes = note.get("点赞数", 0)
        company_stats[primary]["total_likes"] += likes if isinstance(likes, int) else 0

    for company, stats in sorted(company_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        ws.cell(row=row, column=1, value=company)
        ws.cell(row=row, column=2, value=stats["count"])
        avg_likes = stats["total_likes"] / stats["count"] if stats["count"] > 0 else 0
        ws.cell(row=row, column=3, value=round(avg_likes, 1))
        row += 1

    # 按技术方向统计
    row += 1
    ws.cell(row=row, column=1, value="三、按技术方向统计").font = section_font
    row += 1
    ws.cell(row=row, column=1, value="技术方向").font = Font(bold=True)
    ws.cell(row=row, column=2, value="笔记数").font = Font(bold=True)
    row += 1

    tech_stats: dict[str, int] = {}
    for note in notes:
        tech = note.get("岗位方向", "未分类") or "未分类"
        for t in tech.split(","):
            t = t.strip()
            tech_stats[t] = tech_stats.get(t, 0) + 1

    for tech, count in sorted(tech_stats.items(), key=lambda x: x[1], reverse=True):
        ws.cell(row=row, column=1, value=tech)
        ws.cell(row=row, column=2, value=count)
        row += 1

    # 列宽
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 15


def export_to_excel(
    notes: list[dict],
    output_path: Optional[str] = None,
    append: bool = True,
) -> str:
    """
    将笔记数据导出到 Excel 文件。

    :param notes: 笔记数据列表
    :param output_path: 输出路径，默认使用配置中的路径
    :param append: 是否追加到现有文件
    :return: 输出文件路径
    """
    if not output_path:
        os.makedirs(DATA_DIR, exist_ok=True)
        output_path = os.path.join(DATA_DIR, OUTPUT_EXCEL)

    existing_notes = []

    # 如果是追加模式且文件存在，读取已有数据
    if append and os.path.exists(output_path):
        try:
            existing_wb = load_workbook(output_path)
            ws = existing_wb["全部笔记"] if "全部笔记" in existing_wb.sheetnames else existing_wb.active
            if ws is not None:
                headers_row = [cell.value for cell in ws[1]]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    note_dict = {}
                    for idx, header in enumerate(headers_row):
                        if idx < len(row) and header is not None:
                            note_dict[header] = row[idx]
                    if note_dict.get("笔记ID"):
                        existing_notes.append(note_dict)
            existing_wb.close()
            logger.info(f"从现有文件加载了 {len(existing_notes)} 条记录")
        except Exception as e:
            logger.warning(f"读取现有Excel文件失败: {e}，将创建新文件")

    # 合并数据（去重）
    existing_ids = {n.get("笔记ID") for n in existing_notes}
    new_notes = [n for n in notes if n.get("笔记ID") not in existing_ids]
    all_notes = existing_notes + new_notes

    if not all_notes:
        logger.warning("没有数据可以导出")
        return output_path, []

    # 按发布时间排序（最新在前）
    all_notes.sort(key=lambda x: x.get("发布时间") or "", reverse=True)

    # 创建工作簿
    wb = create_workbook()
    ws = wb.active

    # 写入全部数据
    add_notes_to_sheet(ws, all_notes)

    # 创建公司分Sheet
    create_company_sheets(wb, all_notes)

    # 创建统计摘要
    create_summary_sheet(wb, all_notes)

    # 保存
    wb.save(output_path)
    logger.info(f"Excel 文件已保存: {output_path}")
    logger.info(f"  总计: {len(all_notes)} 条 (新增: {len(new_notes)} 条)")

    return output_path, all_notes
