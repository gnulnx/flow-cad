import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const standaloneSource = readFileSync(resolve(process.cwd(), '../index.html'), 'utf8')

describe('standalone viewer metrics display', () => {
  it('uses the Three.js utility module namespace so the standalone module loads', () => {
    expect(standaloneSource).toContain("import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js'")
    expect(standaloneSource).not.toContain("import { BufferGeometryUtils } from 'three/addons/utils/BufferGeometryUtils.js'")
    expect(standaloneSource).not.toContain('setFromGeometry')
  })

  it('passes original geometry metrics to the status bar instead of scaled render geometry', () => {
    expect(standaloneSource).toContain('updateStatusBar(filename, originalMetrics)')

    const updateStatusBar = standaloneSource.match(/function updateStatusBar\(filename, metrics\) \{[\s\S]*?\n        \}/)?.[0]

    expect(updateStatusBar).toBeTruthy()
    expect(updateStatusBar).toContain('metrics.triangleCount')
    expect(updateStatusBar).toContain('metrics.size')
    expect(updateStatusBar).not.toContain('setFromGeometry')
    expect(updateStatusBar).not.toContain('geometry')
  })
})
