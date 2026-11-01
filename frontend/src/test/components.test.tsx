import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  EmptyState,
  PeriodToggle,
  ProgressBar,
  StatTile,
  VerdictBadge,
  WhatIfSlider,
  fmtRub,
  fmtShort,
} from '../design/components'

describe('fmtShort / fmtRub', () => {
  it('систематизирует большие числа', () => {
    expect(fmtShort(1_840_000)).toBe('1.84M')
    expect(fmtShort(12_400)).toBe('12.4K')
    expect(fmtShort(1_000_000_000)).toBe('1.00B')
    expect(fmtShort(42)).toBe('42')
    expect(fmtShort(null)).toBe('—')
  })
  it('добавляет рубли', () => {
    expect(fmtRub(1_840_000)).toBe('1.84M ₽')
    expect(fmtRub(null)).toBe('—')
  })
})

describe('StatTile', () => {
  it('показывает лейбл, значение и TOTAL-строку', () => {
    render(<StatTile label="PROFIT / MO" value="+1.84M ₽" total="TOTAL $6,000 / 12,000" />)
    expect(screen.getByText('PROFIT / MO')).toBeTruthy()
    expect(screen.getByText('+1.84M ₽')).toBeTruthy()
    expect(screen.getByText(/TOTAL/)).toBeTruthy()
  })
  it('кебаб-меню кликабельно', () => {
    let clicked = false
    render(<StatTile label="X" value="1" onMenu={() => { clicked = true }} menu="меню" />)
    fireEvent.click(screen.getByTitle('меню'))
    expect(clicked).toBe(true)
  })
})

describe('VerdictBadge', () => {
  it('красит вердикты по семантике', () => {
    const { container: okC } = render(<VerdictBadge verdict="OK" />)
    expect(okC.querySelector('.verdict.ok')).toBeTruthy()
    const { container: warnC } = render(<VerdictBadge verdict="WARN" />)
    expect(warnC.querySelector('.verdict.warn')).toBeTruthy()
    const { container: blockC } = render(<VerdictBadge verdict="BLOCK" />)
    expect(blockC.querySelector('.verdict.danger')).toBeTruthy()
    expect(screen.getAllByText(/OK|WARN|BLOCK/).length).toBeGreaterThanOrEqual(3)
  })
})

describe('ProgressBar', () => {
  it('заполняется пропорционально', () => {
    const { container } = render(<ProgressBar value={0.5} />)
    const fill = container.querySelector('.progress-fill') as HTMLElement
    expect(fill.style.width).toBe('50%')
  })
})

describe('PeriodToggle', () => {
  it('переключает период', () => {
    let current = '7D'
    const { rerender } = render(<PeriodToggle periods={['7D', '30D']} active={current} onSelect={(p) => { current = p }} />)
    fireEvent.click(screen.getByText('30D'))
    expect(current).toBe('30D')
    rerender(<PeriodToggle periods={['7D', '30D']} active={current} onSelect={(p) => { current = p }} />)
    expect(screen.getByText('30D').className).toContain('active')
  })
})

describe('WhatIfSlider', () => {
  it('двигает значение и блокируется', () => {
    let v = 5
    render(<WhatIfSlider label="discount" value={v} min={0} max={10} step={1} onChange={(x) => { v = x }} />)
    const input = screen.getByRole('slider') as HTMLInputElement
    fireEvent.change(input, { target: { value: '8' } })
    expect(v).toBe(8)
  })
  it('disabled-состояние запрещает ввод', () => {
    render(<WhatIfSlider label="age" value={30} min={0} max={100} step={1} onChange={() => {}} disabled />)
    expect((screen.getByRole('slider') as HTMLInputElement).disabled).toBe(true)
  })
})

describe('EmptyState', () => {
  it('зывает к действию', () => {
    render(<EmptyState label="EMPTY HANGAR" text="Моделей нет" actionLabel="NEW MODEL" onAction={() => {}} />)
    expect(screen.getByText('EMPTY HANGAR')).toBeTruthy()
    expect(screen.getByText('Моделей нет')).toBeTruthy()
    expect(screen.getByTitle('NEW MODEL')).toBeTruthy()
  })
})
