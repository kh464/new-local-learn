import { describe, expect, it } from 'vitest'

import {
  formatBooleanZh,
  formatExecutionModeZh,
  formatFallbackTextZh,
  formatTaskStageZh,
  formatTaskStateZh,
} from './copy'

describe('copy helpers', () => {
  describe('formatTaskStateZh', () => {
    const mappings: [string, string][] = [
      ['queued', '排队中'],
      ['running', '执行中'],
      ['succeeded', '成功'],
      ['completed', '已完成'],
      ['failed', '失败'],
      ['cancelled', '已取消'],
    ]

    for (const [input, expected] of mappings) {
      it(`${input} maps to ${expected}`, () => {
        expect(formatTaskStateZh(input)).toBe(expected)
      })
    }

    it('returns 无 for empty/blank/none/null/undefined input', () => {
      expect(formatTaskStateZh()).toBe('无')
      expect(formatTaskStateZh(null)).toBe('无')
      expect(formatTaskStateZh('')).toBe('无')
      expect(formatTaskStateZh('   ')).toBe('无')
      expect(formatTaskStateZh('none')).toBe('无')
    })

    it('returns 特殊 tokens for unknown/not detected', () => {
      expect(formatTaskStateZh('unknown')).toBe('未知')
      expect(formatTaskStateZh('not detected')).toBe('未检测到')
    })

    it('returns original text for other unknown values even if whitespace exists', () => {
      expect(formatTaskStateZh('custom-state')).toBe('custom-state')
      expect(formatTaskStateZh('  custom-state  ')).toBe('  custom-state  ')
    })

    it('handles case-insensitive known tokens', () => {
      expect(formatTaskStateZh('Queued')).toBe('排队中')
    })
  })

  describe('formatTaskStageZh', () => {
    const mappings: [string, string][] = [
      ['fetch_repo', '拉取代码'],
      ['scan_tree', '扫描目录'],
      ['detect_stack', '识别栈'],
      ['analyze_backend', '分析后端'],
      ['analyze_frontend', '分析前端'],
      ['build_doc', '生成文档'],
      ['finalize', '完成'],
    ]

    for (const [input, expected] of mappings) {
      it(`${input} maps to ${expected}`, () => {
        expect(formatTaskStageZh(input)).toBe(expected)
      })
    }

    it('returns 无 for empty/blank/none/null/undefined input', () => {
      expect(formatTaskStageZh()).toBe('无')
      expect(formatTaskStageZh(null)).toBe('无')
      expect(formatTaskStageZh('')).toBe('无')
      expect(formatTaskStageZh('   ')).toBe('无')
      expect(formatTaskStageZh('none')).toBe('无')
    })

    it('returns 特殊标记 for unknown/not detected', () => {
      expect(formatTaskStageZh('unknown')).toBe('未知')
      expect(formatTaskStageZh('not detected')).toBe('未检测到')
    })

    it('reuses original text for unknown stage with whitespace', () => {
      expect(formatTaskStageZh('  weird-stage  ')).toBe('  weird-stage  ')
    })

    it('handles uppercase known stages', () => {
      expect(formatTaskStageZh('FETCH_REPO')).toBe('拉取代码')
    })
  })

  describe('formatExecutionModeZh', () => {
    const mappings: [string, string][] = [
      ['deterministic', '确定性'],
      ['llm', '大模型'],
      ['fallback', '兜底'],
      ['agent', '助手'],
    ]

    for (const [input, expected] of mappings) {
      it(`${input} maps to ${expected}`, () => {
        expect(formatExecutionModeZh(input)).toBe(expected)
      })
    }

    it('returns 计划中 for undefined or null', () => {
      expect(formatExecutionModeZh()).toBe('计划中')
      expect(formatExecutionModeZh(null)).toBe('计划中')
    })

    it('returns 无 for empty/blank/none input', () => {
      expect(formatExecutionModeZh('')).toBe('无')
      expect(formatExecutionModeZh('   ')).toBe('无')
      expect(formatExecutionModeZh('none')).toBe('无')
    })

    it('returns special fallbacks for unknown/not detected', () => {
      expect(formatExecutionModeZh('unknown')).toBe('未知')
      expect(formatExecutionModeZh('not detected')).toBe('未检测到')
    })

    it('handles case-insensitive known tokens', () => {
      expect(formatExecutionModeZh('LLM')).toBe('大模型')
    })

    it('returns unknown values verbatim', () => {
      expect(formatExecutionModeZh('experimental')).toBe('experimental')
    })
  })

  describe('formatBooleanZh', () => {
    it('true maps to 是', () => {
      expect(formatBooleanZh(true)).toBe('是')
    })

    it('false maps to 否', () => {
      expect(formatBooleanZh(false)).toBe('否')
    })
  })

  describe('formatFallbackTextZh', () => {
    it('maps empty/blank/none/null/undefined to 无', () => {
      expect(formatFallbackTextZh('')).toBe('无')
      expect(formatFallbackTextZh('   ')).toBe('无')
      expect(formatFallbackTextZh('none')).toBe('无')
      expect(formatFallbackTextZh(undefined)).toBe('无')
      expect(formatFallbackTextZh(null)).toBe('无')
    })

    it('maps unknown to 未知 and not detected to 未检测到', () => {
      expect(formatFallbackTextZh('unknown')).toBe('未知')
      expect(formatFallbackTextZh('not detected')).toBe('未检测到')
    })

    it('returns other values verbatim', () => {
      expect(formatFallbackTextZh('custom')).toBe('custom')
    })
  })
})
