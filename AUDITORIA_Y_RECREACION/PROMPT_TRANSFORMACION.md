# PROMPT PARA SISTEMA DE TRANSFORMACIÓN DE ARCHIVOS

## CONTEXTO
Estás construyendo el módulo de transformación de un sistema OCR industrial. Este módulo recibe texto estructurado (JSON) y lo convierte a múltiples formatos de salida (XLSX, CSV, DOCX, TXT, JSON, formatos ERP).

## ARQUITECTURA DEL MÓDULO DE TRANSFORMACIÓN

```
transformacion/
├── __init__.py
├── receptor_datos.py        # Recibe datos estructurados
├── transformador.py         # Transforma datos internos
├── exportadores/
│   ├── __init__.py
│   ├── base.py              # Interfaz base
│   ├── xlsx_exporter.py     # Exportador Excel
│   ├── csv_exporter.py      # Exportador CSV
│   ├── docx_exporter.py     # Exportador Word
│   ├── txt_exporter.py      # Exportador texto plano
│   ├── json_exporter.py     # Exportador JSON
│   └── erp/
│       ├── __init__.py
│       ├── base_erp.py      # Interfaz ERP base
│       ├── odoo_csv.py      # Odoo CSV
│       ├── odoo_xml.py      # Odoo XML
│       ├── sap_csv.py       # SAP BAPI
│       └── journal_csv.py   # Diario contable
├── formateador.py           # Formateo de datos
├── validador_export.py      # Validación pre-export
├── sidecar_generator.py     # Genera archivos sidecar
└── orquestador.py           # Coordina transformación
```

---

## 1. RECEPTOR DE DATOS

```python
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from enum import Enum

class DataType(Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CONTRACT = "contract"
    GENERAL = "general"
    ACCOUNTING = "accounting"

@dataclass
class ExtractedField:
    name: str
    value: Any
    confidence: float
    raw_value: Optional[str] = None
    data_type: str = "string"

@dataclass
class StructuredDocument:
    document_id: str
    filename: str
    content_type: DataType
    fields: list[ExtractedField]
    raw_text: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    extraction_timestamp: datetime = field(default_factory=datetime.now)
    backend_used: str = ""
    confidence: float = 0.0

class DataReceiver:
    """Recibe y valida datos estructurados"""
    
    REQUIRED_FIELDS = {
        DataType.INVOICE: ["invoice_number", "date", "total"],
        DataType.RECEIPT: ["receipt_number", "date", "amount"],
        DataType.CONTRACT: ["contract_id", "parties", "date"],
        DataType.ACCOUNTING: ["account", "debit", "credit"],
    }
    
    def receive(
        self,
        structured_data: dict,
        ocr_text: str,
        metadata: dict
    ) -> StructuredDocument:
        # 1. Detectar tipo
        content_type = self._detect_type(structured_data)
        
        # 2. Extraer campos
        fields = self._extract_fields(structured_data)
        
        # 3. Validar campos requeridos
        self._validate_required(fields, content_type)
        
        return StructuredDocument(
            document_id=metadata.get("document_id", str(uuid.uuid4())),
            filename=metadata.get("filename", "unknown"),
            content_type=content_type,
            fields=fields,
            raw_text=ocr_text,
            metadata=metadata,
            extraction_timestamp=datetime.now(),
            backend_used=metadata.get("backend", ""),
            confidence=metadata.get("confidence", 0.0)
        )
    
    def _detect_type(self, data: dict) -> DataType:
        """Detecta tipo de documento"""
        indicators = {
            DataType.INVOICE: ["invoice_number", "factura", "invoice"],
            DataType.RECEIPT: ["receipt_number", "recibo", "receipt"],
            DataType.CONTRACT: ["contract_id", "contrato", "contract"],
            DataType.ACCOUNTING: ["account", "cuenta", "debit", "credit"],
        }
        
        for dtype, keywords in indicators.items():
            for keyword in keywords:
                if keyword in str(data).lower():
                    return dtype
        
        return DataType.GENERAL
    
    def _extract_fields(self, data: dict) -> list[ExtractedField]:
        """Extrae campos del dato"""
        fields = []
        for key, value in data.items():
            fields.append(ExtractedField(
                name=key,
                value=value,
                confidence=data.get(f"{key}_confidence", 0.8),
                raw_value=str(value),
                data_type=type(value).__name__
            ))
        return fields
```

---

## 2. EXPORTADOR BASE

```python
from abc import ABC, abstractmethod
from pathlib import Path

class Exporter(ABC):
    """Interfaz base para exportadores"""
    
    @property
    @abstractmethod
    def format_name(self) -> str: ...
    
    @property
    @abstractmethod
    def file_extension(self) -> str: ...
    
    @property
    @abstractmethod
    def mime_type(self) -> str: ...
    
    @abstractmethod
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult: ...
    
    @abstractmethod
    def validate_options(self, options: dict) -> bool: ...

@dataclass
class ExportResult:
    file_path: Path
    file_size: int
    records_exported: int
    format: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)
```

---

## 3. EXPORTADOR EXCEL (XLSX)

```python
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

class XLSXExporter(Exporter):
    """Exportador Excel con formato profesional"""
    
    format_name = "xlsx"
    file_extension = ".xlsx"
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        options = options or {}
        
        # 1. Preparar datos
        df = self._documents_to_dataframe(documents)
        
        # 2. Aplicar formato
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
            
            # 3. Aplicar estilos
            self._apply_styles(writer, df, options)
            
            # 4. Añadir resumen (si se solicita)
            if options.get("include_summary", True):
                self._add_summary_sheet(writer, documents)
        
        # 5. Generar sidecar
        sidecar_path = output_path.with_suffix('.json')
        self._generate_sidecar(documents, sidecar_path)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
    
    def _documents_to_dataframe(self, documents: list[StructuredDocument]) -> pd.DataFrame:
        """Convierte documentos a DataFrame"""
        rows = []
        for doc in documents:
            row = {
                "ID": doc.document_id,
                "Archivo": doc.filename,
                "Tipo": doc.content_type.value,
                "Backend": doc.backend_used,
                "Confianza": f"{doc.confidence:.1%}",
                "Fecha Extracción": doc.extraction_timestamp.isoformat(),
            }
            
            # Añadir campos específicos
            for field in doc.fields:
                row[field.name] = field.value
            
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _apply_styles(self, writer, df: pd.DataFrame, options: dict):
        """Aplica estilos profesionales"""
        worksheet = writer.sheets['Datos']
        
        # Header style
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Data style
        data_font = Font(size=10)
        data_alignment = Alignment(vertical="center", wrap_text=True)
        
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.font = data_font
                cell.alignment = data_alignment
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    def _add_summary_sheet(self, writer, documents: list[StructuredDocument]):
        """Añade hoja de resumen"""
        summary_data = {
            "Total documentos": len(documents),
            "Confianza promedio": f"{sum(d.confidence for d in documents) / len(documents):.1%}",
            "Backends utilizados": list(set(d.backend_used for d in documents)),
            "Tipos de documento": list(set(d.content_type.value for d in documents)),
        }
        
        summary_df = pd.DataFrame([summary_data])
        summary_df.to_excel(writer, index=False, sheet_name='Resumen')
```

---

## 4. EXPORTADOR CSV

```python
import csv
import codecs

class CSVExporter(Exporter):
    """Exportador CSV con encoding UTF-8 BOM"""
    
    format_name = "csv"
    file_extension = ".csv"
    mime_type = "text/csv"
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        options = options or {}
        delimiter = options.get("delimiter", ",")
        encoding = options.get("encoding", "utf-8-sig")
        
        # Preparar datos
        df = self._documents_to_dataframe(documents)
        
        # Exportar
        df.to_csv(
            output_path,
            index=False,
            encoding=encoding,
            sep=delimiter,
            quoting=csv.QUOTE_ALL
        )
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
```

---

## 5. EXPORTADOR WORD (DOCX)

```python
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

class DOCXExporter(Exporter):
    """Exportador Word con formato profesional"""
    
    format_name = "docx"
    file_extension = ".docx"
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        doc = Document()
        
        # Título
        title = doc.add_heading('Reporte de Extracción OCR', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Información general
        doc.add_paragraph(f'Total de documentos: {len(documents)}')
        doc.add_paragraph(f'Fecha de exportación: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        
        # Documentos
        for i, document in enumerate(documents, 1):
            doc.add_heading(f'Documento {i}: {document.filename}', level=1)
            
            # Metadata
            table = doc.add_table(rows=4, cols=2)
            table.style = 'Table Grid'
            
            cells = table.rows[0].cells
            cells[0].text = 'ID'
            cells[1].text = document.document_id
            
            cells = table.rows[1].cells
            cells[0].text = 'Tipo'
            cells[1].text = document.content_type.value
            
            cells = table.rows[2].cells
            cells[0].text = 'Backend'
            cells[1].text = document.backend_used
            
            cells = table.rows[3].cells
            cells[0].text = 'Confianza'
            cells[1].text = f'{document.confidence:.1%}'
            
            # Campos
            doc.add_heading('Campos Extraídos', level=2)
            
            field_table = doc.add_table(rows=len(document.fields) + 1, cols=3)
            field_table.style = 'Table Grid'
            
            # Header
            header_cells = field_table.rows[0].cells
            header_cells[0].text = 'Campo'
            header_cells[1].text = 'Valor'
            header_cells[2].text = 'Confianza'
            
            # Data
            for j, field in enumerate(document.fields, 1):
                row_cells = field_table.rows[j].cells
                row_cells[0].text = field.name
                row_cells[1].text = str(field.value)
                row_cells[2].text = f'{field.confidence:.1%}'
            
            doc.add_page_break()
        
        doc.save(output_path)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
```

---

## 6. EXPORTADOR JSON

```python
import json

class JSONExporter(Exporter):
    """Exportador JSON con formato legible"""
    
    format_name = "json"
    file_extension = ".json"
    mime_type = "application/json"
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        options = options or {}
        indent = options.get("indent", 2)
        
        # Serializar documentos
        data = {
            "metadata": {
                "total_documents": len(documents),
                "export_timestamp": datetime.now().isoformat(),
                "format_version": "1.0"
            },
            "documents": [self._serialize_document(doc) for doc in documents]
        }
        
        # Exportar
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
    
    def _serialize_document(self, doc: StructuredDocument) -> dict:
        """Serializa documento a dict"""
        return {
            "document_id": doc.document_id,
            "filename": doc.filename,
            "content_type": doc.content_type.value,
            "fields": [
                {
                    "name": f.name,
                    "value": f.value,
                    "confidence": f.confidence,
                    "data_type": f.data_type
                }
                for f in doc.fields
            ],
            "raw_text": doc.raw_text,
            "metadata": doc.metadata,
            "extraction_timestamp": doc.extraction_timestamp.isoformat(),
            "backend_used": doc.backend_used,
            "confidence": doc.confidence
        }
```

---

## 7. EXPORTADORES ERP

### 7.1 Odoo CSV

```python
class OdooCSVExporter(Exporter):
    """Exportador para Odoo CSV import"""
    
    format_name = "odoo_csv"
    file_extension = ".csv"
    
    ODOO_FIELDS = {
        "invoice": [
            "invoice_id", "partner_id", "invoice_date", "invoice_line_ids",
            "currency_id", "amount_total", "amount_tax", "state"
        ],
        "journal": [
            "date", "journal_id", "account_id", "debit", "credit",
            "name", "partner_id", "ref"
        ]
    }
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        doc_type = options.get("doc_type", "invoice")
        fields = self.ODOO_FIELDS.get(doc_type, self.ODOO_FIELDS["invoice"])
        
        rows = []
        for doc in documents:
            row = self._map_to_odoo(doc, doc_type)
            rows.append(row)
        
        df = pd.DataFrame(rows, columns=fields)
        df.to_csv(output_path, index=False)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
    
    def _map_to_odoo(self, doc: StructuredDocument, doc_type: str) -> dict:
        """Mapea campos a formato Odoo"""
        fields_dict = {f.name: f.value for f in doc.fields}
        
        if doc_type == "invoice":
            return {
                "invoice_id": fields_dict.get("invoice_number"),
                "partner_id": fields_dict.get("vendor_name"),
                "invoice_date": fields_dict.get("date"),
                "amount_total": fields_dict.get("total"),
                "amount_tax": fields_dict.get("tax"),
                "currency_id": fields_dict.get("currency", "USD"),
                "state": "draft"
            }
        
        return fields_dict
```

### 7.2 Odoo XML

```python
from xml.etree import ElementTree as ET

class OdooXMLExporter(Exporter):
    """Exportador para Odoo XML import"""
    
    format_name = "odoo_xml"
    file_extension = ".xml"
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        root = ET.Element("odoo")
        
        for doc in documents:
            record = ET.SubElement(root, "record", model="account.move")
            
            fields_dict = {f.name: f.value for f in doc.fields}
            
            # Invoice fields
            ET.SubElement(record, "field", name="move_type").text = "in_invoice"
            ET.SubElement(record, "field", name="invoice_id").text = str(fields_dict.get("invoice_number", ""))
            ET.SubElement(record, "field", name="partner_id").text = str(fields_dict.get("vendor_name", ""))
            ET.SubElement(record, "field", name="invoice_date").text = str(fields_dict.get("date", ""))
            ET.SubElement(record, "field", name="amount_total").text = str(fields_dict.get("total", 0))
        
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(output_path, encoding="unicode", xml_declaration=True)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
```

### 7.3 SAP BAPI CSV

```python
class SAPCSVExporter(Exporter):
    """Exportador para SAP BAPI_ACC_DOCUMENT_POST"""
    
    format_name = "sap_csv"
    file_extension = ".csv"
    
    SAP_FIELDS = [
        "DocumentHeader", "DOC_TYPE", "BUS_AREA", "COMP_CODE",
        "DOC_DATE", "PSTNG_DATE", "HEADER_TXT", "OBJ_TYPE",
        "OBJ_KEY", "OBJ_SYS", "BUS_ACT", "FISC_YEAR",
        "ACCOUNTGL", "ACCOUNTRECEIVABLE", "ACCOUNTTAX",
        "CURRENCYAMOUNT", "CRSREFERENCENO", "REASONCODE",
        "ITEM", "GL_ACCOUNT", "ITEM_TEXT", "TYPE", "AMOUNT",
        "COSTCENTER", "ORDERID", "MATERIALNUMBER", "VENDOR"
    ]
    
    async def export(
        self,
        documents: list[StructuredDocument],
        output_path: Path,
        options: dict = None
    ) -> ExportResult:
        rows = []
        for doc in documents:
            row = self._map_to_sap(doc)
            rows.append(row)
        
        df = pd.DataFrame(rows, columns=self.SAP_FIELDS)
        df.to_csv(output_path, index=False)
        
        return ExportResult(
            file_path=output_path,
            file_size=output_path.stat().st_size,
            records_exported=len(documents),
            format=self.format_name,
            timestamp=datetime.now()
        )
    
    def _map_to_sap(self, doc: StructuredDocument) -> dict:
        """Mapea campos a formato SAP"""
        fields_dict = {f.name: f.value for f in doc.fields}
        
        return {
            "DocumentHeader": "X",
            "DOC_TYPE": "KR",
            "DOC_DATE": fields_dict.get("date"),
            "PSTNG_DATE": fields_dict.get("date"),
            "HEADER_TXT": fields_dict.get("invoice_number"),
            "COMP_CODE": options.get("company_code", "1000"),
            "CURRENCYAMOUNT": fields_dict.get("currency", "USD"),
            "GL_ACCOUNT": fields_dict.get("gl_account", ""),
            "VENDOR": fields_dict.get("vendor_code", ""),
            "AMOUNT": fields_dict.get("total", 0),
        }
```

---

## 8. ORQUESTADOR DE EXPORTACIÓN

```python
from pathlib import Path

class ExportOrchestrator:
    """Coordina la exportación a múltiples formatos"""
    
    def __init__(self):
        self.exporters = {
            "xlsx": XLSXExporter(),
            "csv": CSVExporter(),
            "docx": DOCXExporter(),
            "txt": TXTExporter(),
            "json": JSONExporter(),
            "erp_odoo_csv": OdooCSVExporter(),
            "erp_odoo_xml": OdooXMLExporter(),
            "erp_sap": SAPCSVExporter(),
        }
    
    async def export(
        self,
        documents: list[StructuredDocument],
        format: str,
        output_dir: Path,
        options: dict = None
    ) -> ExportResult:
        # 1. Obtener exportador
        exporter = self.exporters.get(format)
        if not exporter:
            raise ValueError(f"Formato no soportado: {format}")
        
        # 2. Validar opciones
        if not exporter.validate_options(options or {}):
            raise ValueError("Opciones inválidas")
        
        # 3. Crear directorio
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 4. Generar nombre de archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ocr_export_{timestamp}{exporter.file_extension}"
        output_path = output_dir / filename
        
        # 5. Exportar
        result = await exporter.export(documents, output_path, options)
        
        # 6. Generar sidecar JSON
        sidecar_path = output_path.with_suffix('.json')
        self._generate_sidecar(documents, sidecar_path, result)
        
        return result
    
    def _generate_sidecar(
        self,
        documents: list[StructuredDocument],
        sidecar_path: Path,
        export_result: ExportResult
    ):
        """Genera archivo sidecar con metadata"""
        import json
        
        sidecar = {
            "export_info": {
                "format": export_result.format,
                "file_path": str(export_result.file_path),
                "file_size": export_result.file_size,
                "records_exported": export_result.records_exported,
                "timestamp": export_result.timestamp.isoformat()
            },
            "documents": [
                {
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "confidence": doc.confidence,
                    "backend_used": doc.backend_used
                }
                for doc in documents
            ]
        }
        
        with open(sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)
```

---

## 9. FLUJO COMPLETO

```
1. Recibir datos estructurados (JSON del OCR)
   ↓
2. Detectar tipo de documento
   ↓
3. Extraer y validar campos
   ↓
4. Seleccionar formato de exportación
   ↓
5. Ejecutar exportador específico
   ↓
6. Aplicar formato y estilos
   ↓
7. Generar archivo sidecar
   ↓
8. Devolver ExportResult
```

---

## 10. FORMATOS SOPORTADOS

| Formato | Uso | Archivos generados |
|---------|-----|-------------------|
| XLSX | Reportes, análisis | .xlsx + .json (sidecar) |
| CSV | Intercambio de datos | .csv + .json |
| DOCX | Documentos formales | .docx + .json |
| TXT | Texto plano | .txt + .json |
| JSON | APIs, integraciones | .json |
| Odoo CSV | ERP Odoo | .csv + .json |
| Odoo XML | ERP Odoo | .xml + .json |
| SAP CSV | ERP SAP | .csv + .json |
| Journal CSV | Contabilidad | .csv + .json |
