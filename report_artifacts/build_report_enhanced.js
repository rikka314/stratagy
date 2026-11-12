#!/usr/bin/env node
/**
 * Build an enhanced DOCX course report from outline.json and screenshots.
 *
 * Usage: node build_report_enhanced.js <outline.json> <screenshots_dir> <output.docx>
 */

const {
    AlignmentType,
    BorderStyle,
    Document,
    Footer,
    ImageRun,
    LineRuleType,
    PageBreak,
    PageNumber,
    Packer,
    Paragraph,
    ShadingType,
    Table,
    TableCell,
    TableLayoutType,
    TableRow,
    TextRun,
    VerticalAlign,
    WidthType,
} = require("docx");
const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);
if (args.length < 3) {
    console.error("Usage: node build_report_enhanced.js <outline.json> <screenshots_dir> <output.docx>");
    process.exit(1);
}

const outlinePath = path.resolve(args[0]);
const shotsDir = path.resolve(args[1]);
const outputPath = path.resolve(args[2]);
const outlineText = fs.readFileSync(outlinePath, "utf-8").replace(/^\uFEFF/, "");
const outline = JSON.parse(outlineText);

const F = outline.format || {};
const PRESET = outline.design_preset || {};
const H1F = F.h1Font || "SimHei";
const BODYF = F.bodyFont || "SimSun";
const CODEF = F.codeFont || "Consolas";
const H1SZ = (F.h1Size || 16) * 2;
const H2SZ = (F.h2Size || 14) * 2;
const BODYSZ = (F.bodySize || 10.5) * 2;
const CODESZ = (F.codeSize || 9) * 2;
const LINE_SPACING = (F.lineSpacing || 22) * 20;
const MARGIN_TWIPS = Math.round((F.marginInches || 1) * 1440);
const PAGE_WIDTH_TWIPS = 11906;
const PAGE_HEIGHT_TWIPS = 16838;
const CONTENT_WIDTH_TWIPS = PAGE_WIDTH_TWIPS - 2 * MARGIN_TWIPS;
const CONTENT_HEIGHT_TWIPS = PAGE_HEIGHT_TWIPS - 2 * MARGIN_TWIPS;
const TABLE_HEADER_FILL = PRESET.tableHeaderColor || "D9EAF7";
const CAPTION_COLOR = PRESET.captionColor || "44546A";
const CODE_BACKGROUND = PRESET.codeBackground || "F4F6F8";
const CELL_MARGIN = { top: 80, bottom: 80, left: 100, right: 100 };

function font(name) {
    return { ascii: name, hAnsi: name, eastAsia: name };
}

function paragraph(text, opts = {}) {
    return new Paragraph({
        alignment: opts.alignment || AlignmentType.JUSTIFIED,
        keepNext: opts.keepNext || false,
        keepLines: opts.keepLines || false,
        spacing: {
            line: opts.line || LINE_SPACING,
            lineRule: LineRuleType.EXACTLY,
            before: opts.before || 0,
            after: opts.after || 0,
        },
        indent: opts.firstLine ? { firstLine: opts.firstLine } : undefined,
        children: [
            new TextRun({
                text: String(text ?? ""),
                font: font(opts.font || BODYF),
                size: opts.size || BODYSZ,
                bold: opts.bold || false,
                color: opts.color,
            }),
        ],
    });
}

function coverValue(cv, key, fallback = "【请填写】") {
    const value = cv && typeof cv[key] === "string" ? cv[key].trim() : "";
    return value || fallback;
}

function pageBreakParagraph() {
    return new Paragraph({ children: [new PageBreak()] });
}

function calculateColumnWidths(rows) {
    const columnCount = Math.max(...rows.map((row) => row.length));
    const weights = Array.from({ length: columnCount }, (_, columnIndex) => {
        const maxLength = Math.max(
            4,
            ...rows.map((row) => Array.from(String(row[columnIndex] ?? "")).length),
        );
        return Math.min(maxLength, 30);
    });
    const total = weights.reduce((sum, value) => sum + value, 0);
    const minimumWidth = Math.min(1100, Math.floor(CONTENT_WIDTH_TWIPS / columnCount));
    let widths = weights.map((weight) => Math.max(minimumWidth, Math.floor(CONTENT_WIDTH_TWIPS * weight / total)));
    const widthSum = widths.reduce((sum, value) => sum + value, 0);
    widths = widths.map((value) => Math.floor(value * CONTENT_WIDTH_TWIPS / widthSum));
    widths[widths.length - 1] += CONTENT_WIDTH_TWIPS - widths.reduce((sum, value) => sum + value, 0);
    return widths;
}

function makeTable(section) {
    const rows = section.rows || [];
    if (!rows.length) {
        return [];
    }
    const columnWidths = calculateColumnWidths(rows);
    const tableRows = rows.map((row, rowIndex) => new TableRow({
        tableHeader: rowIndex === 0,
        cantSplit: true,
        children: columnWidths.map((columnWidth, columnIndex) => new TableCell({
            width: { size: columnWidth, type: WidthType.DXA },
            margins: CELL_MARGIN,
            verticalAlign: VerticalAlign.CENTER,
            shading: rowIndex === 0
                ? { fill: TABLE_HEADER_FILL, type: ShadingType.CLEAR, color: "auto" }
                : undefined,
            children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { line: LINE_SPACING, lineRule: LineRuleType.EXACTLY },
                children: [new TextRun({
                    text: String(row[columnIndex] ?? ""),
                    font: font(BODYF),
                    size: BODYSZ,
                    bold: rowIndex === 0,
                })],
            })],
        })),
    }));
    return [new Table({
        rows: tableRows,
        width: { size: CONTENT_WIDTH_TWIPS, type: WidthType.DXA },
        columnWidths,
        layout: TableLayoutType.FIXED,
        margins: CELL_MARGIN,
        borders: {
            top: { style: BorderStyle.SINGLE, size: 4, color: "7F8C8D" },
            bottom: { style: BorderStyle.SINGLE, size: 4, color: "7F8C8D" },
            left: { style: BorderStyle.SINGLE, size: 4, color: "7F8C8D" },
            right: { style: BorderStyle.SINGLE, size: 4, color: "7F8C8D" },
            insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "B7C9D6" },
            insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "B7C9D6" },
        },
    })];
}

function makeCodeBlock(section) {
    const lines = Array.isArray(section.lines) ? section.lines : [];
    const codeParagraphs = (lines.length ? lines : [""]).map((line) => new Paragraph({
        alignment: AlignmentType.LEFT,
        spacing: { line: 280, lineRule: LineRuleType.EXACTLY, before: 0, after: 0 },
        children: [new TextRun({
            text: line.length ? line : " ",
            font: font(CODEF),
            size: CODESZ,
        })],
    }));
    return [new Table({
        rows: [new TableRow({
            cantSplit: true,
            children: [new TableCell({
                width: { size: CONTENT_WIDTH_TWIPS, type: WidthType.DXA },
                margins: { top: 100, bottom: 100, left: 140, right: 140 },
                shading: { fill: CODE_BACKGROUND, type: ShadingType.CLEAR, color: "auto" },
                borders: {
                    top: { style: BorderStyle.SINGLE, size: 2, color: "D0D7DE" },
                    bottom: { style: BorderStyle.SINGLE, size: 2, color: "D0D7DE" },
                    left: { style: BorderStyle.SINGLE, size: 2, color: "D0D7DE" },
                    right: { style: BorderStyle.SINGLE, size: 2, color: "D0D7DE" },
                },
                children: codeParagraphs,
            })],
        })],
        width: { size: CONTENT_WIDTH_TWIPS, type: WidthType.DXA },
        columnWidths: [CONTENT_WIDTH_TWIPS],
        layout: TableLayoutType.FIXED,
    })];
}

function constrainedImageSize(section) {
    const requestedWidth = Number(section.width) || 500;
    const requestedHeight = Number(section.height) || 320;
    const maxWidthPx = CONTENT_WIDTH_TWIPS / 15;
    const maxHeightPx = CONTENT_HEIGHT_TWIPS / 15;
    const scale = Math.min(1, maxWidthPx / requestedWidth, maxHeightPx / requestedHeight);
    return {
        width: Math.max(1, Math.round(requestedWidth * scale)),
        height: Math.max(1, Math.round(requestedHeight * scale)),
    };
}

function imageType(fileName) {
    const extension = path.extname(fileName).slice(1).toLowerCase();
    return extension === "jpg" ? "jpeg" : extension;
}

function makeImage(section) {
    const imagePath = path.join(shotsDir, section.file);
    const size = constrainedImageSize(section);
    const imageParagraph = new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 40, after: 40 },
        keepNext: true,
        keepLines: true,
        children: [new ImageRun({
            data: fs.readFileSync(imagePath),
            transformation: size,
            type: imageType(section.file),
        })],
    });
    const captionParagraph = paragraph(section.caption || "", {
        alignment: AlignmentType.CENTER,
        size: BODYSZ,
        color: CAPTION_COLOR,
        before: 20,
        after: 40,
        keepLines: true,
    });
    return [
        imageParagraph,
        captionParagraph,
        paragraph(" ", { line: 120, after: 40 }),
    ];
}

function validateImageReferences() {
    const imageSections = (outline.sections || []).filter((section) => section.type === "image");
    const missing = imageSections
        .map((section) => section.file)
        .filter((file) => !file || !fs.existsSync(path.join(shotsDir, file)));
    if (missing.length) {
        throw new Error(`Missing image references (${missing.length}): ${[...new Set(missing)].join(", ")}`);
    }
    console.log(`Validated ${imageSections.length} image references (${new Set(imageSections.map((section) => section.file)).size} source files).`);
}

function buildCover(children) {
    const cv = outline.cover;
    if (!cv) {
        return;
    }
    for (let i = 0; i < 4; i += 1) children.push(paragraph(" "));
    children.push(paragraph(coverValue(cv, "title", "课程设计报告"), {
        alignment: AlignmentType.CENTER,
        size: H1SZ + 4,
        bold: true,
    }));
    children.push(paragraph(coverValue(cv, "semester"), {
        alignment: AlignmentType.CENTER,
        size: H1SZ,
    }));
    children.push(paragraph(" "));
    children.push(paragraph(`课程名：${coverValue(cv, "course")}`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    children.push(paragraph(`设计题目：${coverValue(cv, "topic")}`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    children.push(paragraph(" "));
    children.push(paragraph(`专业班级：${coverValue(cv, "class")}`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    children.push(paragraph(`姓名：${coverValue(cv, "authors")}`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    children.push(paragraph(`指导教师：${coverValue(cv, "advisor")}`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    for (let i = 0; i < 6; i += 1) children.push(paragraph(" "));
    children.push(paragraph(`${coverValue(cv, "institution")} 制`, { alignment: AlignmentType.CENTER, size: H2SZ }));
    children.push(pageBreakParagraph());
}

async function build() {
    validateImageReferences();
    const children = [];
    buildCover(children);

    let h1Count = 0;
    for (const section of outline.sections || []) {
        if (section.type === "h1") {
            if (h1Count > 0) children.push(pageBreakParagraph());
            children.push(paragraph(section.text, {
                alignment: AlignmentType.CENTER,
                font: H1F,
                size: H1SZ,
                bold: true,
                before: 240,
                after: 120,
                keepNext: true,
            }));
            h1Count += 1;
        } else if (section.type === "h2") {
            const headingText = /^5\./.test(section.text || "")
                ? `　${section.text}`
                : section.text;
            children.push(paragraph(headingText, {
                font: H1F,
                size: H2SZ,
                bold: true,
                before: 200,
                after: 80,
                keepNext: true,
            }));
        } else if (section.type === "body") {
            children.push(paragraph(section.text, {
                firstLine: section.indent ? 480 : undefined,
                bold: section.bold || false,
            }));
        } else if (section.type === "pagebreak") {
            children.push(pageBreakParagraph());
        } else if (section.type === "empty") {
            children.push(paragraph(" "));
        } else if (section.type === "code") {
            children.push(...makeCodeBlock(section));
        } else if (section.type === "image") {
            if (/^图5-/.test(section.caption || "")) {
                children.push(pageBreakParagraph());
            }
            children.push(...makeImage(section));
        } else if (section.type === "table") {
            children.push(...makeTable(section));
        }
    }

    const footer = new Footer({
        children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({
                children: [PageNumber.CURRENT],
                font: font(BODYF),
                size: BODYSZ,
            })],
        })],
    });

    const doc = new Document({
        sections: [{
            properties: {
                page: {
                    size: { width: PAGE_WIDTH_TWIPS, height: PAGE_HEIGHT_TWIPS },
                    margin: {
                        top: MARGIN_TWIPS,
                        right: MARGIN_TWIPS,
                        bottom: MARGIN_TWIPS,
                        left: MARGIN_TWIPS,
                    },
                },
            },
            footers: { default: footer },
            children,
        }],
    });

    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(outputPath, Buffer.from(buffer));
    console.log(`DOCX saved: ${outputPath} (${(buffer.length / 1024 / 1024).toFixed(2)} MiB, ${children.length} top-level elements)`);
}

build().catch((error) => {
    console.error(error);
    process.exit(1);
});
