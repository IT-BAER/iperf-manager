import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export interface SelectOption {
  value: string
  label: string
}

interface Props {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  disabled?: boolean
  className?: string
  placeholder?: string
  emptyLabel?: string
  fullWidth?: boolean
  id?: string
  'aria-label'?: string
}

/**
 * Fully themed dropdown replacing native <select>.
 * Trigger looks like .btn; option list uses surface tokens so it matches the dark UI.
 */
export function SelectInput({ value, onChange, options, disabled, className = '', placeholder = '—', emptyLabel = 'No options', fullWidth = false, id, 'aria-label': ariaLabel }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [listStyle, setListStyle] = useState<React.CSSProperties>({})

  /* Position the portal list and keep it inside the viewport bounds */
  const updatePosition = useCallback(() => {
    const rect = btnRef.current?.getBoundingClientRect()
    if (!rect) return

    const viewportPadding = 8
    const anchorGap = 6
    // At least as wide as the trigger; long labels may widen it up to 320px, then truncate.
    const menuWidth = Math.min(Math.max(rect.width, 320), window.innerWidth - viewportPadding * 2)
    const availableBelow = window.innerHeight - rect.bottom - viewportPadding - anchorGap
    const availableAbove = rect.top - viewportPadding - anchorGap
    const openUpward = availableBelow < 160 && availableAbove > availableBelow
    const maxHeight = Math.max(96, openUpward ? availableAbove : availableBelow)
    const estimatedHeight = Math.min(maxHeight, Math.max(32, options.length * 32))
    const top = openUpward
      ? Math.max(viewportPadding, rect.top - estimatedHeight - anchorGap)
      : rect.bottom + anchorGap

    // Near the right edge, grow leftwards from the trigger's right edge instead of overflowing.
    const alignRight = rect.left + menuWidth > window.innerWidth - viewportPadding
    const horizontal = alignRight
      ? { right: Math.max(viewportPadding, window.innerWidth - rect.right) }
      : { left: Math.max(rect.left, viewportPadding) }

    setListStyle({
      position: 'fixed',
      top,
      ...horizontal,
      minWidth: rect.width,
      maxWidth: menuWidth,
      maxHeight,
      overflowY: 'auto',
      zIndex: 2147483647,
    })
  }, [options.length])

  /* Close on outside click */
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      const inTrigger = !!rootRef.current?.contains(target)
      const inMenu = !!listRef.current?.contains(target)
      if (!inTrigger && !inMenu) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  /* Keep menu anchored while the viewport moves */
  useEffect(() => {
    if (!open) return

    const onViewportChange = () => updatePosition()
    onViewportChange()
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)

    return () => {
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
    }
  }, [open, updatePosition])

  /* Close on Escape */
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  const selected = options.find(o => o.value === value)
  const label = selected ? selected.label : placeholder

  return (
    <div ref={rootRef} className={fullWidth ? 'relative block w-full' : 'relative inline-block'}>
      <button
        ref={btnRef}
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => {
          if (!open) updatePosition()
          setOpen(v => !v)
        }}
        className={`btn justify-between gap-2 pr-2.5 ${fullWidth ? 'w-full' : ''} ${className}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
      >
        <span className={`truncate ${selected ? '' : 'text-fg-3 font-normal'}`} title={selected ? selected.label : undefined}>{label}</span>
        <i
          className={`fa-solid fa-chevron-down text-[9px] text-fg-3 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && createPortal(
        <div
          ref={listRef}
          role="listbox"
          style={listStyle}
          className="rounded-sm border border-line bg-surface-raised shadow-[0_10px_28px_rgba(0,0,0,0.55)] overflow-hidden"
        >
          {options.length === 0 && (
            <div className="px-3 py-1.5 text-[13px] text-fg-3 whitespace-nowrap">{emptyLabel}</div>
          )}
          {options.map(opt => {
            const isSelected = opt.value === value
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                title={opt.label}
                onClick={() => { onChange(opt.value); setOpen(false) }}
                className={`block w-full text-left px-3 py-1.5 text-[13px] transition-colors duration-100 whitespace-nowrap truncate
                  ${isSelected
                    ? 'text-accent font-medium bg-accent/10'
                    : 'text-fg hover:bg-surface-hover'
                  }`}
              >
                {opt.label}
              </button>
            )
          })}
        </div>,
        document.body
      )}
    </div>
  )
}
