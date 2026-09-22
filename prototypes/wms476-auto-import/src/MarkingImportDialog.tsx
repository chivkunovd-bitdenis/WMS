import { useEffect, useMemo, useRef, useState } from 'react'
import {
  autoFailedRows,
  autoSuccessGroupsFull,
  autoSuccessGroupsPartial,
  catalog,
  formatFileSize,
  manualLoadedPerProduct,
  previewGroupSeeds,
  sampleAutoFiles,
  type AutoGroup,
  type CatalogRow,
  type DemoScenario,
  type FailedRow,
  type SampleFile,
} from './data'
import { buildFailedCodesPdf, downloadBlob } from './pdf'

type Props = {
  open: boolean
  scenario: DemoScenario
  onClose: () => void
}

type Stage =
  | 'picker'
  | 'processing-auto'
  | 'result-auto-partial'
  | 'result-auto-full'
  | 'result-auto-error'
  | 'processing-manual'
  | 'result-manual'

type PreviewGroupState = {
  key: string
  gtin: string
  codesCount: number
  suggestedTitle: string
  title: string
  productSearch: string
  productIds: Set<string>
  showAll: boolean
}

type ManualPerProductRow = {
  product: CatalogRow
  groupKey: string
  loadedCount: number
}

type ManualResult = {
  productCount: number
  loadedCount: number
  skippedCount: number
  perProduct: ManualPerProductRow[]
}

const PRODUCT_SEARCH_INITIAL_LIMIT = 6

function filterProducts(rows: CatalogRow[], search: string): CatalogRow[] {
  const needle = search.trim().toLowerCase()
  if (!needle) return rows
  return rows.filter((row) => {
    const hay = `${row.sku} ${row.vendorCode} ${row.name} ${row.size ?? ''} ${row.barcode}`.toLowerCase()
    return hay.includes(needle)
  })
}

function seedsToPreviewGroups(existing: PreviewGroupState[]): PreviewGroupState[] {
  const byKey = new Map(existing.map((g) => [g.key, g] as const))
  return previewGroupSeeds.map((seed) => {
    const prev = byKey.get(seed.key)
    if (prev) {
      return {
        ...prev,
        gtin: seed.gtin,
        codesCount: seed.codesCount,
        suggestedTitle: seed.suggestedTitle,
      }
    }
    return {
      key: seed.key,
      gtin: seed.gtin,
      codesCount: seed.codesCount,
      suggestedTitle: seed.suggestedTitle,
      title: seed.suggestedTitle,
      productSearch: '',
      productIds: new Set<string>(),
      showAll: false,
    }
  })
}

function CheckboxIcon({ checked }: { checked: boolean }) {
  return (
    <span className={`checkbox${checked ? ' is-checked' : ''}`} role="presentation">
      {checked ? (
        <svg viewBox="0 0 12 12" className="checkbox-inner" aria-hidden>
          <path
            d="M2 6.5 L5 9 L10 3"
            stroke="currentColor"
            strokeWidth="2"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : null}
    </span>
  )
}

export function MarkingImportDialog({ open, scenario, onClose }: Props) {
  const [stage, setStage] = useState<Stage>('picker')
  const [files, setFiles] = useState<SampleFile[]>([])
  const [parsingBusy, setParsingBusy] = useState(false)
  const [previewGroups, setPreviewGroups] = useState<PreviewGroupState[]>([])
  const [processingProgress, setProcessingProgress] = useState(0)
  const [processingLine, setProcessingLine] = useState('')
  const [manualResult, setManualResult] = useState<ManualResult | null>(null)
  const processingTimersRef = useRef<number[]>([])
  const parsingTimerRef = useRef<number | null>(null)

  const totalSelected = useMemo(
    () => previewGroups.reduce((sum, g) => sum + g.productIds.size, 0),
    [previewGroups],
  )
  const canRunAuto =
    files.length > 0 && !parsingBusy && previewGroups.length > 0 && totalSelected === 0
  const canRunManual =
    files.length > 0 && !parsingBusy && previewGroups.length > 0 && totalSelected > 0

  const clearProcessingTimers = () => {
    for (const id of processingTimersRef.current) {
      window.clearTimeout(id)
    }
    processingTimersRef.current = []
  }

  const clearParsingTimer = () => {
    if (parsingTimerRef.current != null) {
      window.clearTimeout(parsingTimerRef.current)
      parsingTimerRef.current = null
    }
  }

  const resetInputs = () => {
    clearParsingTimer()
    setFiles([])
    setPreviewGroups([])
    setParsingBusy(false)
    setManualResult(null)
    setProcessingProgress(0)
    setProcessingLine('')
  }

  useEffect(() => {
    if (open) {
      setStage('picker')
      resetInputs()
    } else {
      clearProcessingTimers()
      clearParsingTimer()
    }
    return () => {
      clearProcessingTimers()
      clearParsingTimer()
    }
  }, [open, scenario])

  const runPreview = () => {
    clearParsingTimer()
    setParsingBusy(true)
    const timer = window.setTimeout(() => {
      parsingTimerRef.current = null
      setPreviewGroups((prev) => seedsToPreviewGroups(prev))
      setParsingBusy(false)
    }, 380)
    parsingTimerRef.current = timer
  }

  const addSampleFile = () => {
    if (stage !== 'picker') return
    const next = sampleAutoFiles[files.length % sampleAutoFiles.length]
    if (!next) return
    if (files.some((f) => f.name === next.name)) return
    const nextFiles = [...files, next]
    setFiles(nextFiles)
    runPreview()
  }

  const removeFileAt = (index: number) => {
    if (stage !== 'picker') return
    const nextFiles = files.filter((_, i) => i !== index)
    setFiles(nextFiles)
    if (nextFiles.length === 0) {
      clearParsingTimer()
      setParsingBusy(false)
      setPreviewGroups([])
    } else {
      runPreview()
    }
  }

  const updateGroup = (key: string, patch: (group: PreviewGroupState) => PreviewGroupState) => {
    setPreviewGroups((prev) => prev.map((g) => (g.key === key ? patch(g) : g)))
  }

  const toggleGroupProduct = (groupKey: string, productId: string) => {
    updateGroup(groupKey, (group) => {
      const next = new Set(group.productIds)
      if (next.has(productId)) next.delete(productId)
      else next.add(productId)
      return { ...group, productIds: next }
    })
  }

  const stageForScenario = (target: DemoScenario): Stage => {
    if (target === 'full') return 'result-auto-full'
    if (target === 'error') return 'result-auto-error'
    return 'result-auto-partial'
  }

  const runAutoScenario = (override?: DemoScenario) => {
    if (files.length === 0 || parsingBusy || previewGroups.length === 0) return
    clearProcessingTimers()
    const effective = override ?? scenario
    setStage('processing-auto')
    setProcessingProgress(0)
    setProcessingLine('Читаем файлы…')
    const steps: { at: number; progress: number; line: string }[] =
      effective === 'error'
        ? [
            { at: 300, progress: 22, line: 'Читаем файлы…' },
            { at: 900, progress: 55, line: 'Извлекаем коды маркировки…' },
            { at: 1500, progress: 78, line: 'Сопоставляем с каталогом селлера…' },
          ]
        : [
            { at: 300, progress: 18, line: 'Читаем файлы…' },
            { at: 900, progress: 42, line: 'Извлекаем коды маркировки…' },
            { at: 1500, progress: 68, line: 'Сопоставляем с каталогом селлера…' },
            { at: 2100, progress: 92, line: 'Формируем группы для загрузки…' },
          ]
    for (const step of steps) {
      const timer = window.setTimeout(() => {
        setProcessingProgress(step.progress)
        setProcessingLine(step.line)
      }, step.at)
      processingTimersRef.current.push(timer)
    }
    const finalDelay = effective === 'error' ? 1900 : 2500
    const finalTimer = window.setTimeout(() => {
      setProcessingProgress(100)
      setStage(stageForScenario(effective))
    }, finalDelay)
    processingTimersRef.current.push(finalTimer)
  }

  const buildManualResultFromGroups = (): ManualResult => {
    const perProduct: ManualPerProductRow[] = []
    const seenProducts = new Set<string>()
    for (const group of previewGroups) {
      for (const productId of group.productIds) {
        if (seenProducts.has(productId)) continue
        seenProducts.add(productId)
        const product = catalog.find((row) => row.id === productId)
        if (!product) continue
        perProduct.push({
          product,
          groupKey: group.key,
          loadedCount: manualLoadedPerProduct[productId] ?? 20,
        })
      }
    }
    const loadedCount = perProduct.reduce((sum, row) => sum + row.loadedCount, 0)
    const skippedCount = perProduct.length > 1 ? 3 : 1
    return {
      productCount: perProduct.length,
      loadedCount,
      skippedCount,
      perProduct,
    }
  }

  const runManualScenario = () => {
    if (!canRunManual) return
    clearProcessingTimers()
    setStage('processing-manual')
    setProcessingProgress(0)
    setProcessingLine('Готовим ручную загрузку…')
    const steps: { at: number; progress: number; line: string }[] = [
      { at: 260, progress: 30, line: 'Проверяем формат файла…' },
      { at: 700, progress: 60, line: 'Привязываем коды к выбранным товарам…' },
      { at: 1100, progress: 90, line: 'Сохраняем в пул селлера…' },
    ]
    for (const step of steps) {
      const timer = window.setTimeout(() => {
        setProcessingProgress(step.progress)
        setProcessingLine(step.line)
      }, step.at)
      processingTimersRef.current.push(timer)
    }
    const finalTimer = window.setTimeout(() => {
      setProcessingProgress(100)
      setManualResult(buildManualResultFromGroups())
      setStage('result-manual')
    }, 1400)
    processingTimersRef.current.push(finalTimer)
  }

  const backToPicker = () => {
    clearProcessingTimers()
    setStage('picker')
    resetInputs()
  }

  const pickAnotherFile = () => {
    clearProcessingTimers()
    clearParsingTimer()
    setStage('picker')
    setFiles([])
    setPreviewGroups([])
    setParsingBusy(false)
    setProcessingProgress(0)
    setProcessingLine('')
  }

  const retryAfterError = () => {
    runAutoScenario('partial')
  }

  const downloadFailedPdf = () => {
    const blob = buildFailedCodesPdf(autoFailedRows)
    downloadBlob(blob, 'WMS-476-nepodgruzhennye-kizy.pdf')
  }

  if (!open) return null

  const isResultAuto =
    stage === 'result-auto-partial' ||
    stage === 'result-auto-full' ||
    stage === 'result-auto-error'
  const isResult = isResultAuto || stage === 'result-manual'

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-dialog-title"
      onClick={onClose}
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2 id="import-dialog-title" className="modal-title">
            Загрузка КИЗ
          </h2>
          <button
            type="button"
            className="modal-close"
            aria-label="Закрыть"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="modal-body">
          {stage === 'picker' ? (
            <PickerBody
              files={files}
              parsingBusy={parsingBusy}
              previewGroups={previewGroups}
              onDropzoneClick={addSampleFile}
              onRemoveFile={removeFileAt}
              onUpdateGroup={updateGroup}
              onToggleGroupProduct={toggleGroupProduct}
            />
          ) : null}

          {stage === 'processing-auto' || stage === 'processing-manual' ? (
            <ProcessingBody
              title={
                stage === 'processing-auto'
                  ? 'Распознаём коды…'
                  : 'Загружаем коды на выбранные товары…'
              }
              line={processingLine}
              progress={processingProgress}
            />
          ) : null}

          {stage === 'result-auto-partial' ? (
            <AutoResultBody
              groups={autoSuccessGroupsPartial}
              failed={autoFailedRows}
              onDownloadFailed={downloadFailedPdf}
            />
          ) : null}

          {stage === 'result-auto-full' ? (
            <AutoResultBody groups={autoSuccessGroupsFull} failed={[]} />
          ) : null}

          {stage === 'result-auto-error' ? (
            <AutoErrorBody
              files={files}
              onRetry={retryAfterError}
              onPickAnotherFile={pickAnotherFile}
            />
          ) : null}

          {stage === 'result-manual' && manualResult ? (
            <ManualResultBody result={manualResult} />
          ) : null}
        </div>

        <footer className="modal-footer">
          <ModalFooter
            stage={stage}
            canRunAuto={canRunAuto}
            canRunManual={canRunManual}
            selectedCount={totalSelected}
            groupsCount={previewGroups.length}
            onRunAuto={() => runAutoScenario()}
            onRunManual={runManualScenario}
            onBackToPicker={backToPicker}
            onClose={onClose}
            showBackToPicker={isResult && stage !== 'result-auto-error'}
          />
        </footer>
      </div>
    </div>
  )
}

function ModalFooter({
  stage,
  canRunAuto,
  canRunManual,
  selectedCount,
  groupsCount,
  onRunAuto,
  onRunManual,
  onBackToPicker,
  onClose,
  showBackToPicker,
}: {
  stage: Stage
  canRunAuto: boolean
  canRunManual: boolean
  selectedCount: number
  groupsCount: number
  onRunAuto: () => void
  onRunManual: () => void
  onBackToPicker: () => void
  onClose: () => void
  showBackToPicker: boolean
}) {
  if (stage === 'picker') {
    const showManual = selectedCount > 0
    return (
      <>
        <button type="button" className="btn btn-text" onClick={onClose}>
          Отмена
        </button>
        {showManual ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canRunManual}
            onClick={onRunManual}
          >
            Загрузить
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canRunAuto || groupsCount === 0}
            onClick={onRunAuto}
          >
            Распознать автоматически
          </button>
        )}
      </>
    )
  }

  if (stage === 'processing-auto' || stage === 'processing-manual') {
    return (
      <button type="button" className="btn btn-text" disabled>
        Отмена
      </button>
    )
  }

  if (stage === 'result-auto-error') {
    return (
      <button type="button" className="btn btn-text" onClick={onClose}>
        Закрыть
      </button>
    )
  }

  return (
    <>
      {showBackToPicker ? (
        <button type="button" className="btn btn-outlined" onClick={onBackToPicker}>
          Загрузить ещё
        </button>
      ) : null}
      <button type="button" className="btn btn-primary" onClick={onClose}>
        Готово
      </button>
    </>
  )
}

function PickerBody({
  files,
  parsingBusy,
  previewGroups,
  onDropzoneClick,
  onRemoveFile,
  onUpdateGroup,
  onToggleGroupProduct,
}: {
  files: SampleFile[]
  parsingBusy: boolean
  previewGroups: PreviewGroupState[]
  onDropzoneClick: () => void
  onRemoveFile: (index: number) => void
  onUpdateGroup: (
    key: string,
    patch: (group: PreviewGroupState) => PreviewGroupState,
  ) => void
  onToggleGroupProduct: (groupKey: string, productId: string) => void
}) {
  return (
    <>
      <button
        type="button"
        className="dropzone"
        onClick={onDropzoneClick}
        aria-label="Добавить тестовый файл"
      >
        <div className="dropzone-icon" aria-hidden>
          ⬆
        </div>
        <div className="dropzone-primary">
          Перетащите PDF или CSV из «Честного знака»
        </div>
        <div className="dropzone-secondary">
          В макете нажмите сюда, чтобы добавить тестовый файл ({sampleAutoFiles.length} шт. в
          комплекте)
        </div>
        {files.length > 0 ? (
          <div className="dropzone-files">
            {files.map((file, index) => (
              <span key={`${file.name}-${index}`} className="chip">
                <span className="chip-label" title={file.name}>
                  {file.name}
                </span>
                <span className="text-muted" style={{ fontSize: 11 }}>
                  {formatFileSize(file.size)}
                </span>
                <button
                  type="button"
                  className="chip-close"
                  aria-label={`Убрать ${file.name}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onRemoveFile(index)
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
      </button>

      {parsingBusy ? (
        <div className="row" data-testid="parsing-line">
          <div className="spinner spinner-sm" aria-hidden />
          <span className="text-caption text-secondary">Разбор файла…</span>
        </div>
      ) : null}

      {previewGroups.map((group) => (
        <PreviewGroupCard
          key={group.key}
          group={group}
          onUpdateGroup={onUpdateGroup}
          onToggleProduct={onToggleGroupProduct}
        />
      ))}
    </>
  )
}

function PreviewGroupCard({
  group,
  onUpdateGroup,
  onToggleProduct,
}: {
  group: PreviewGroupState
  onUpdateGroup: (
    key: string,
    patch: (group: PreviewGroupState) => PreviewGroupState,
  ) => void
  onToggleProduct: (groupKey: string, productId: string) => void
}) {
  const filtered = filterProducts(catalog, group.productSearch)
  const truncated = filtered.length > PRODUCT_SEARCH_INITIAL_LIMIT && !group.showAll
  const visible = truncated ? filtered.slice(0, PRODUCT_SEARCH_INITIAL_LIMIT) : filtered
  const shortGtin = group.gtin.slice(-4)

  return (
    <div className="paper paper-padded preview-group">
      <div className="row-space" style={{ gap: 8 }}>
        <div>
          <div className="section-title">
            GTIN …{shortGtin}
            <span className="counter">{group.codesCount} КМ</span>
          </div>
          <div className="text-caption text-secondary mono">Полный GTIN: {group.gtin}</div>
        </div>
      </div>
      <label className="field-label" htmlFor={`title-${group.key}`}>
        Название пула
      </label>
      <input
        id={`title-${group.key}`}
        className="input"
        value={group.title}
        onChange={(e) =>
          onUpdateGroup(group.key, (g) => ({ ...g, title: e.target.value }))
        }
      />
      <label className="field-label" htmlFor={`search-${group.key}`}>
        Поиск товаров
      </label>
      <div className="field-search">
        <span className="field-search-icon" aria-hidden>
          🔍
        </span>
        <input
          id={`search-${group.key}`}
          className="input"
          placeholder="Артикул, название или штрихкод"
          value={group.productSearch}
          onChange={(e) =>
            onUpdateGroup(group.key, (g) => ({
              ...g,
              productSearch: e.target.value,
              showAll: false,
            }))
          }
        />
      </div>
      <div className="preview-products">
        {visible.length === 0 ? (
          <div className="product-row-empty">
            По запросу ничего не нашли. Очистите поле или измените запрос.
          </div>
        ) : (
          visible.map((product) => {
            const checked = group.productIds.has(product.id)
            return (
              <div
                key={product.id}
                className={`product-row${checked ? ' is-checked' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => onToggleProduct(group.key, product.id)}
                onKeyDown={(e) => {
                  if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault()
                    onToggleProduct(group.key, product.id)
                  }
                }}
              >
                <CheckboxIcon checked={checked} />
                <div className="product-cell-name">
                  <div className="product-sku">{product.sku}</div>
                  <div className="product-name" title={product.name}>
                    {product.name}
                  </div>
                </div>
                <div className="product-cell-mobile-hide">
                  <div className="product-meta">Артикул: {product.vendorCode}</div>
                  <div className="product-barcode">ШК: {product.barcode}</div>
                </div>
                <div className="product-cell-mobile-hide">
                  <span className="chip chip-outlined">{product.size ?? '—'}</span>
                </div>
                <div className="product-cell-mobile-hide" style={{ textAlign: 'right' }}>
                  <span className="text-caption text-secondary">{checked ? 'выбран' : ' '}</span>
                </div>
              </div>
            )
          })
        )}
      </div>
      {truncated ? (
        <div className="row" style={{ gap: 8 }}>
          <span className="text-caption text-secondary">
            Показаны первые {PRODUCT_SEARCH_INITIAL_LIMIT} из {filtered.length}
            {group.productIds.size > 0 ? ` · выбрано ${group.productIds.size}` : ''}
          </span>
          <button
            type="button"
            className="btn btn-text btn-sm"
            onClick={() =>
              onUpdateGroup(group.key, (g) => ({ ...g, showAll: true }))
            }
          >
            Показать ещё
          </button>
        </div>
      ) : null}
    </div>
  )
}

function ProcessingBody({
  title,
  line,
  progress,
}: {
  title: string
  line: string
  progress: number
}) {
  return (
    <div className="processing" role="status" aria-live="polite">
      <div className="spinner" aria-hidden />
      <div className="processing-line">
        <strong>{title}</strong>
      </div>
      <div className="processing-progress" aria-hidden>
        <div className="processing-progress-bar" style={{ width: `${progress}%` }} />
      </div>
      <div className="text-secondary text-caption">{line || 'Готовим данные…'}</div>
    </div>
  )
}

function AutoResultBody({
  groups,
  failed,
  onDownloadFailed,
}: {
  groups: AutoGroup[]
  failed: FailedRow[]
  onDownloadFailed?: () => void
}) {
  const totalLoaded = groups.reduce((sum, g) => sum + g.loadedCount, 0)
  const failedCount = failed.length
  const isEmptyFailed = failedCount === 0

  return (
    <>
      <div className="alert alert-success">
        <div>
          <strong>Загружено {totalLoaded} КИЗ</strong> · распознано и привязано автоматически к{' '}
          {groups.length} товарам.
        </div>
      </div>

      <div className="paper table-wrap">
        <table className="wms-table">
          <thead>
            <tr>
              <th style={{ minWidth: 260 }}>Артикул</th>
              <th style={{ minWidth: 90 }}>Размер</th>
              <th style={{ minWidth: 160 }}>Штрихкод</th>
              <th className="col-num" style={{ minWidth: 140 }}>
                Загружено КИЗ
              </th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.key}>
                <td>
                  <div className="product-sku">{group.sku}</div>
                  <div className="product-name" title={group.productName}>
                    {group.productName}
                  </div>
                </td>
                <td>
                  <span className="chip chip-outlined">{group.size ?? '—'}</span>
                </td>
                <td className="mono">{group.barcode}</td>
                <td className="col-num">
                  <strong>{group.loadedCount}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={`failed-block${isEmptyFailed ? ' is-empty' : ''}`}>
        <div className="failed-header">
          <div className="failed-header-title">Не подгружено — {failedCount} КИЗ</div>
          {!isEmptyFailed && onDownloadFailed ? (
            <button
              type="button"
              className="btn btn-danger-outlined btn-sm"
              onClick={onDownloadFailed}
            >
              Скачать PDF с неподгруженными КИЗами
            </button>
          ) : null}
        </div>
        {isEmptyFailed ? (
          <div className="text-caption text-secondary">
            В файле не осталось этикеток без привязки — все КИЗ распознаны.
          </div>
        ) : (
          <>
            <div className="text-caption text-secondary">
              Успешная часть уже сохранена. Эти коды можно перепроверить и загрузить вручную позже.
            </div>
            <div className="table-wrap" style={{ borderTop: '1px solid rgba(185, 28, 28, 0.2)' }}>
              <table className="wms-table">
                <thead>
                  <tr>
                    <th style={{ minWidth: 260 }}>Код маркировки</th>
                    <th>Причина</th>
                  </tr>
                </thead>
                <tbody>
                  {failed.map((row) => (
                    <tr key={row.key}>
                      <td className="mono" style={{ wordBreak: 'break-all' }}>
                        {row.markingCode}
                      </td>
                      <td>{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  )
}

function AutoErrorBody({
  files,
  onRetry,
  onPickAnotherFile,
}: {
  files: SampleFile[]
  onRetry: () => void
  onPickAnotherFile: () => void
}) {
  return (
    <>
      <div className="alert alert-error" role="alert">
        <div>
          <strong>Распознавание не завершено.</strong> Результат не сохранён — ни один КИЗ из
          файла не был привязан к товарам. Попробуйте повторить или выберите другой файл.
        </div>
      </div>

      <div className="paper paper-padded stack-tight">
        <div className="text-caption text-secondary">Файлы, с которыми не получилось:</div>
        <div className="row">
          {files.length === 0 ? (
            <span className="chip">Файлы уже сняты</span>
          ) : (
            files.map((file, index) => (
              <span key={`${file.name}-${index}`} className="chip">
                <span className="chip-label" title={file.name}>
                  {file.name}
                </span>
                <span className="text-muted" style={{ fontSize: 11 }}>
                  {formatFileSize(file.size)}
                </span>
              </span>
            ))
          )}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn btn-primary" onClick={onRetry}>
            Попробовать снова
          </button>
          <button type="button" className="btn btn-outlined" onClick={onPickAnotherFile}>
            Выбрать другой файл
          </button>
        </div>
      </div>
    </>
  )
}

function ManualResultBody({ result }: { result: ManualResult }) {
  return (
    <>
      <div className="alert alert-success">
        <div>
          <strong>Загружено {result.loadedCount} КИЗ</strong> на {result.productCount} выбранных
          товаров. Дубликатов и повреждённых строк пропущено: {result.skippedCount}.
        </div>
      </div>

      <div className="paper table-wrap">
        <table className="wms-table">
          <thead>
            <tr>
              <th style={{ minWidth: 260 }}>Товар</th>
              <th style={{ minWidth: 100 }}>Размер</th>
              <th className="col-num" style={{ minWidth: 140 }}>
                Загружено КИЗ
              </th>
            </tr>
          </thead>
          <tbody>
            {result.perProduct.map(({ product, loadedCount, groupKey }) => (
              <tr key={`${groupKey}-${product.id}`}>
                <td>
                  <div className="product-sku">{product.sku}</div>
                  <div className="product-name" title={product.name}>
                    {product.name}
                  </div>
                </td>
                <td>
                  <span className="chip chip-outlined">{product.size ?? '—'}</span>
                </td>
                <td className="col-num">
                  <strong>{loadedCount}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
