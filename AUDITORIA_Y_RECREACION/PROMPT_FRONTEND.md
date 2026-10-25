# PROMPT PARA RECREACIÓN DEL FRONTEND - OCR INDUSTRIAL

## CONTEXTO
Estás recreando el frontend de un sistema OCR industrial. El frontend debe ser una aplicación web moderna que se comunique con el backend via REST API. Debe soportar drag-and-drop, vista previa de documentos, gestión de prompts, monitoreo en tiempo real y exportación.

## ARQUITECTURA OBJETIVO

```
frontend/
├── public/
│   ├── index.html
│   └── favicon.ico
├── src/
│   ├── main.tsx                    # Entry point
│   ├── App.tsx                     # Router principal
│   ├── api/
│   │   ├── client.ts               # Axios/Fetch client
│   │   ├── endpoints.ts            # API endpoints
│   │   ├── hooks/
│   │   │   ├── useOCR.ts           # Hook OCR principal
│   │   │   ├── useJobs.ts          # Hook gestión trabajos
│   │   │   ├── useBackends.ts      # Hook backends
│   │   │   ├── useExports.ts       # Hook exportación
│   │   │   ├── usePrompts.ts       # Hook prompts
│   │   │   └── useWebSocket.ts     # Hook WebSocket
│   │   └── types/
│   │       └── api.ts              # TypeScript types
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx       # Layout principal
│   │   │   ├── Sidebar.tsx         # Sidebar izquierdo
│   │   │   ├── Header.tsx          # Header superior
│   │   │   └── Footer.tsx          # Footer
│   │   ├── ocr/
│   │   │   ├── FileUploader.tsx    # Drag & drop zone
│   │   │   ├── FileList.tsx        # Lista de archivos
│   │   │   ├── OCRConfig.tsx       # Configuración OCR
│   │   │   ├── BackendSelector.tsx # Selector de backend
│   │   │   ├── PromptEditor.tsx    # Editor de prompts
│   │   │   ├── ProcessingStatus.tsx # Estado de procesamiento
│   │   │   └── OCRResults.tsx      # Resultados OCR
│   │   ├── preview/
│   │   │   ├── DocumentPreview.tsx # Vista previa documento
│   │   │   ├── ImageZoom.tsx       # Zoom de imagen
│   │   │   └── TextComparison.tsx  # Comparación OCR vs original
│   │   ├── export/
│   │   │   ├── ExportPanel.tsx     # Panel de exportación
│   │   │   ├── FormatSelector.tsx  # Selector de formato
│   │   │   └── ExportHistory.tsx   # Historial de exportaciones
│   │   ├── jobs/
│   │   │   ├── JobList.tsx         # Lista de trabajos
│   │   │   ├── JobDetail.tsx       # Detalle de trabajo
│   │   │   └── BatchProgress.tsx   # Progreso de lote
│   │   ├── prompts/
│   │   │   ├── PromptLibrary.tsx   # Biblioteca de prompts
│   │   │   ├── PromptEditor.tsx    # Editor de prompt
│   │   │   └── PromptTemplates.tsx # Templates predefinidos
│   │   ├── dashboard/
│   │   │   ├── MetricsDashboard.tsx # Dashboard de métricas
│   │   │   ├── TelemetryChart.tsx  # Gráfico de telemetría
│   │   │   └── CostTracker.tsx     # Rastreador de costos
│   │   ├── audit/
│   │   │   ├── AuditLog.tsx        # Log de auditoría
│   │   │   └── AuditDetail.tsx     # Detalle de auditoría
│   │   └── common/
│   │       ├── Button.tsx          # Botón reutilizable
│   │       ├── Modal.tsx           # Modal
│   │       ├── Toast.tsx           # Notificaciones
│   │       ├── Spinner.tsx         # Loading spinner
│   │       ├── ErrorBoundary.tsx   # Error boundary
│   │       └── ThemeToggle.tsx     # Toggle dark/light
│   ├── hooks/
│   │   ├── useDebounce.ts          # Debounce hook
│   │   ├── useLocalStorage.ts      # Persistencia local
│   │   ├── useMediaQuery.ts        # Responsive
│   │   └── useTheme.ts             # Tema dark/light
│   ├── store/
│   │   ├── index.ts                # Zustand store
│   │   ├── slices/
│   │   │   ├── ocrSlice.ts         # Estado OCR
│   │   │   ├── jobSlice.ts         # Estado trabajos
│   │   │   ├── uiSlice.ts          # Estado UI
│   │   │   └── settingsSlice.ts    # Configuración
│   ├── utils/
│   │   ├── formatters.ts           # Formateo de datos
│   │   ├── validators.ts           # Validaciones
│   │   ├── constants.ts            # Constantes
│   │   └── helpers.ts              # Utilidades
│   ├── styles/
│   │   ├── globals.css             # Estilos globales
│   │   ├── theme.ts                # Tema Tailwind
│   │   └── animations.css          # Animaciones
│   └── types/
│       ├── index.ts                # Types globales
│       └── ocr.ts                  # Types OCR
├── tailwind.config.js
├── postcss.config.js
├── vite.config.ts
├── tsconfig.json
├── package.json
└── README.md
```

---

## COMPONENTES PRINCIPALES

### 1. FileUploader (Drag & Drop)

```tsx
import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';

interface FileUploaderProps {
  onFilesAccepted: (files: File[]) => void;
  maxFiles?: number;
  accept?: Record<string, string[]>;
}

export function FileUploader({ 
  onFilesAccepted, 
  maxFiles = 50,
  accept = {
    'application/pdf': ['.pdf'],
    'image/*': ['.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp']
  }
}: FileUploaderProps) {
  const [uploading, setUploading] = useState(false);
  
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setUploading(true);
    try {
      await onFilesAccepted(acceptedFiles);
    } finally {
      setUploading(false);
    }
  }, [onFilesAccepted]);
  
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles,
    accept
  });
  
  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-lg p-8
        transition-colors duration-200
        ${isDragActive 
          ? 'border-blue-500 bg-blue-50' 
          : 'border-gray-300 hover:border-gray-400'}
        ${uploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <input {...getInputProps()} />
      
      <div className="text-center">
        <UploadIcon className="mx-auto h-12 w-12 text-gray-400" />
        
        <p className="mt-2 text-sm text-gray-600">
          {isDragActive 
            ? 'Suelta los archivos aquí...'
            : 'Arrastra archivos aquí o haz clic para seleccionar'}
        </p>
        
        <p className="mt-1 text-xs text-gray-500">
          PDF, PNG, JPG, TIFF, BMP (max. 50 archivos)
        </p>
      </div>
    </div>
  );
}
```

### 2. BackendSelector

```tsx
import { useState } from 'react';
import { useBackends } from '@/api/hooks/useBackends';

interface BackendSelectorProps {
  selected: string;
  onChange: (backend: string) => void;
}

export function BackendSelector({ selected, onChange }: BackendSelectorProps) {
  const { backends, loading } = useBackends();
  
  const groupedBackends = {
    free: backends.filter(b => b.type === 'local' || b.type === 'cloud_free'),
    paid: backends.filter(b => b.type === 'cloud_paid')
  };
  
  return (
    <div className="space-y-4">
      <label className="block text-sm font-medium text-gray-700">
        Motor OCR
      </label>
      
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
      >
        <optgroup label="🔄 Automático (Recomendado)">
          <option value="auto">Selección automática</option>
        </optgroup>
        
        <optgroup label="🆓 Gratuitos">
          {groupedBackends.free.map(backend => (
            <option key={backend.id} value={backend.id}>
              {backend.name} - {backend.description}
            </option>
          ))}
        </optgroup>
        
        <optgroup label="💰 De Pago">
          {groupedBackends.paid.map(backend => (
            <option key={backend.id} value={backend.id}>
              {backend.name} - ${backend.costPer1kPages}/1K páginas
            </option>
          ))}
        </optgroup>
      </select>
      
      {selected !== 'auto' && (
        <div className="text-sm text-gray-500">
          <p>Costo estimado: ${backends.find(b => b.id === selected)?.costPer1kPages || 0}/1K páginas</p>
          <p>Formatos soportados: {backends.find(b => b.id === selected)?.supportedFormats.join(', ')}</p>
        </div>
      )}
    </div>
  );
}
```

### 3. OCRConfig

```tsx
import { useState } from 'react';
import { BackendSelector } from './BackendSelector';
import { PromptEditor } from './PromptEditor';

interface OCRConfigProps {
  onConfigChange: (config: OCRConfig) => void;
}

export interface OCRConfig {
  backend: string;
  prompt: string;
  preprocessing: boolean;
  structuring: boolean;
  outputFormat: string;
  language: string;
}

export function OCRConfig({ onConfigChange }: OCRConfigProps) {
  const [config, setConfig] = useState<OCRConfig>({
    backend: 'auto',
    prompt: '',
    preprocessing: true,
    structuring: true,
    outputFormat: 'xlsx',
    language: 'es'
  });
  
  const handleChange = (key: keyof OCRConfig, value: any) => {
    const newConfig = { ...config, [key]: value };
    setConfig(newConfig);
    onConfigChange(newConfig);
  };
  
  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-gray-900">Configuración OCR</h3>
      
      <BackendSelector
        selected={config.backend}
        onChange={(v) => handleChange('backend', v)}
      />
      
      <PromptEditor
        value={config.prompt}
        onChange={(v) => handleChange('prompt', v)}
      />
      
      <div className="space-y-4">
        <h4 className="text-sm font-medium text-gray-700">Opciones</h4>
        
        <label className="flex items-center space-x-3">
          <input
            type="checkbox"
            checked={config.preprocessing}
            onChange={(e) => handleChange('preprocessing', e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600"
          />
          <span className="text-sm text-gray-700">
            Preprocesamiento adaptativo
          </span>
        </label>
        
        <label className="flex items-center space-x-3">
          <input
            type="checkbox"
            checked={config.structuring}
            onChange={(e) => handleChange('structuring', e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600"
          />
          <span className="text-sm text-gray-700">
            Estructurar con LLM
          </span>
        </label>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Formato de salida
          </label>
          <select
            value={config.outputFormat}
            onChange={(e) => handleChange('outputFormat', e.target.value)}
            className="block w-full rounded-md border-gray-300"
          >
            <option value="xlsx">Excel (XLSX)</option>
            <option value="csv">CSV</option>
            <option value="docx">Word (DOCX)</option>
            <option value="txt">Texto plano</option>
            <option value="json">JSON</option>
            <option value="erp_odoo">ERP Odoo</option>
            <option value="erp_sap">ERP SAP</option>
          </select>
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Idioma
          </label>
          <select
            value={config.language}
            onChange={(e) => handleChange('language', e.target.value)}
            className="block w-full rounded-md border-gray-300"
          >
            <option value="es">Español</option>
            <option value="en">Inglés</option>
            <option value="fr">Francés</option>
            <option value="de">Alemán</option>
            <option value="pt">Portugués</option>
            <option value="auto">Auto-detectar</option>
          </select>
        </div>
      </div>
    </div>
  );
}
```

### 4. DocumentPreview

```tsx
import { useState, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';

interface DocumentPreviewProps {
  file: File | null;
  ocrText?: string;
  confidence?: number;
}

export function DocumentPreview({ file, ocrText, confidence }: DocumentPreviewProps) {
  const [rotation, setRotation] = useState(0);
  const [showOCR, setShowOCR] = useState(false);
  
  const fileUrl = file ? URL.createObjectURL(file) : null;
  
  return (
    <div className="flex flex-col h-full bg-gray-100 rounded-lg overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 bg-white border-b">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setRotation(r => r - 90)}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <RotateLeftIcon className="h-5 w-5" />
          </button>
          <button
            onClick={() => setRotation(r => r + 90)}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <RotateRightIcon className="h-5 w-5" />
          </button>
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowOCR(!showOCR)}
            className={`px-3 py-1 rounded text-sm ${
              showOCR 
                ? 'bg-blue-500 text-white' 
                : 'bg-gray-200 text-gray-700'
            }`}
          >
            {showOCR ? 'Ocultar OCR' : 'Mostrar OCR'}
          </button>
          
          {confidence && (
            <span className={`text-sm px-2 py-1 rounded ${
              confidence > 0.8 
                ? 'bg-green-100 text-green-800' 
                : 'bg-yellow-100 text-yellow-800'
            }`}>
              Confianza: {(confidence * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>
      
      {/* Preview */}
      <div className="flex-1 overflow-hidden">
        {showOCR ? (
          <div className="h-full p-4 overflow-auto">
            <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
              {ocrText || 'No hay texto OCR disponible'}
            </pre>
          </div>
        ) : (
          <TransformWrapper>
            <TransformComponent>
              <div 
                className="flex items-center justify-center p-4"
                style={{ transform: `rotate(${rotation}deg)` }}
              >
                {file?.type === 'application/pdf' ? (
                  <iframe
                    src={fileUrl}
                    className="w-full h-full border-0"
                    title="PDF Preview"
                  />
                ) : (
                  <img
                    src={fileUrl}
                    alt="Document preview"
                    className="max-w-full max-h-full object-contain"
                  />
                )}
              </div>
            </TransformComponent>
          </TransformWrapper>
        )}
      </div>
    </div>
  );
}
```

### 5. ProcessingStatus

```tsx
import { useEffect } from 'react';

interface ProcessingStatusProps {
  jobId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  currentFile?: string;
  totalFiles: number;
  processedFiles: number;
  estimatedTime?: number;
  onCancel: () => void;
  onPause: () => void;
}

export function ProcessingStatus({
  jobId,
  status,
  progress,
  currentFile,
  totalFiles,
  processedFiles,
  estimatedTime,
  onCancel,
  onPause
}: ProcessingStatusProps) {
  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800'
  };
  
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">
          Procesando documentos
        </h3>
        
        <span className={`px-3 py-1 rounded-full text-sm ${statusColors[status]}`}>
          {status === 'pending' && 'En cola'}
          {status === 'processing' && 'Procesando...'}
          {status === 'completed' && 'Completado'}
          {status === 'failed' && 'Error'}
        </span>
      </div>
      
      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>Progreso</span>
          <span>{progress}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900">{processedFiles}</div>
          <div className="text-sm text-gray-500">de {totalFiles} archivos</div>
        </div>
        
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900">
            {estimatedTime ? `${Math.ceil(estimatedTime / 60)}m` : '--'}
          </div>
          <div className="text-sm text-gray-500">Tiempo restante</div>
        </div>
        
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900">
            {currentFile ? currentFile.substring(0, 20) + '...' : '--'}
          </div>
          <div className="text-sm text-gray-500">Archivo actual</div>
        </div>
      </div>
      
      {/* Actions */}
      {status === 'processing' && (
        <div className="flex space-x-3">
          <button
            onClick={onPause}
            className="flex-1 px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600"
          >
            Pausar
          </button>
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
          >
            Cancelar
          </button>
        </div>
      )}
    </div>
  );
}
```

### 6. MetricsDashboard

```tsx
import { useEffect, useState } from 'react';
import { Line, Bar, Pie } from 'react-chartjs-2';

interface MetricsDashboardProps {
  metrics: {
    totalDocuments: number;
    totalTokens: number;
    totalCost: number;
    averageConfidence: number;
    backendUsage: Record<string, number>;
    dailyProcessing: Array<{ date: string; count: number }>;
  };
}

export function MetricsDashboard({ metrics }: MetricsDashboardProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Dashboard de Métricas</h2>
      
      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          title="Documentos procesados"
          value={metrics.totalDocuments}
          icon={<DocumentIcon />}
          color="blue"
        />
        <KPICard
          title="Tokens utilizados"
          value={metrics.totalTokens.toLocaleString()}
          icon={<TokenIcon />}
          color="green"
        />
        <KPICard
          title="Costo total"
          value={`$${metrics.totalCost.toFixed(2)}`}
          icon={<CostIcon />}
          color="purple"
        />
        <KPICard
          title="Confianza promedio"
          value={`${(metrics.averageConfidence * 100).toFixed(1)}%`}
          icon={<ConfidenceIcon />}
          color="yellow"
        />
      </div>
      
      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-lg font-medium mb-4">Procesamiento diario</h3>
          <Line data={dailyChartData} />
        </div>
        
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-lg font-medium mb-4">Uso por backend</h3>
          <Bar data={backendChartData} />
        </div>
        
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-lg font-medium mb-4">Distribución de costos</h3>
          <Pie data={costChartData} />
        </div>
        
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-lg font-medium mb-4">Confianza por backend</h3>
          <Bar data={confidenceChartData} />
        </div>
      </div>
    </div>
  );
}
```

---

## HOOKS PERSONALIZADOS

### useOCR Hook

```typescript
import { useState, useCallback } from 'react';
import { api } from '@/api/client';

export function useOCR() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<OCRResult[]>([]);
  
  const processDocument = useCallback(async (
    file: File,
    config: OCRConfig
  ) => {
    setLoading(true);
    setError(null);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('backend', config.backend);
      formData.append('prompt', config.prompt);
      formData.append('output_format', config.outputFormat);
      
      const response = await api.post('/ocr/process', formData);
      
      setResults(prev => [...prev, response.data]);
      return response.data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);
  
  const processBatch = useCallback(async (
    files: File[],
    config: OCRConfig
  ) => {
    setLoading(true);
    setError(null);
    
    try {
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));
      formData.append('backend', config.backend);
      formData.append('prompt', config.prompt);
      
      const response = await api.post('/ocr/batch', formData);
      
      return response.data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);
  
  return {
    loading,
    error,
    results,
    processDocument,
    processBatch,
    clearResults: () => setResults([])
  };
}
```

### useWebSocket Hook

```typescript
import { useEffect, useRef, useState } from 'react';

export function useWebSocket(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  
  useEffect(() => {
    if (!jobId) return;
    
    const ws = new WebSocket(`${import.meta.env.VITE_WS_URL}/jobs/${jobId}`);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setStatus(data.status);
      setProgress(data.progress);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    wsRef.current = ws;
    
    return () => {
      ws.close();
    };
  }, [jobId]);
  
  return { status, progress };
}
```

---

## ESTILOS (Tailwind CSS)

```css
/* globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 221.2 83.2% 53.3%;
  }
  
  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --primary: 217.2 91.2% 59.8%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 224.3 76.3% 48%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

---

## REQUISITOS FINALES

1. **React 18+** con TypeScript
2. **Tailwind CSS** para estilos
3. **Zustand** para estado global
4. **React Query** para data fetching
5. **react-zoom-pan-pinch** para vista previa
6. **chart.js** para gráficos
7. **react-dropzone** para drag & drop
8. **Dark/Light mode** toggle
9. **Responsive** (mobile, tablet, desktop)
10. **WebSocket** para actualizaciones en tiempo real
11. **Error boundaries** para manejo de errores
12. **Loading states** para UX
13. **Accesibilidad** (ARIA labels, keyboard navigation)
14. **Performance** (lazy loading, memoization)
15. **Testing** (unit + integration + E2E con Cypress/Playwright)
