<script setup lang="ts">
/** 产品界面预览：CSS 模拟 Mol* 3D 与 Rosetta 排名表 */
</script>

<template>
  <section class="product-preview">
    <div class="landing-container product-preview__grid">
      <div class="product-preview__copy">
        <p class="product-preview__eyebrow">Platform Preview</p>
        <h2>提交任务后，在同一平台查看结构与排序</h2>
        <p>
          折叠完成后用 Mol* 看复合物与 pLDDT 着色；Rosetta 评价自动生成 ranking.csv，支持 ΔΔG、界面氢键与 clash 标记。
        </p>
        <ul>
          <li>3D 复合物可视化 · 界面残基高亮</li>
          <li>多指标加权排序 · 一键下载 relaxed PDB</li>
          <li>从折叠详情页直接发起结构评价</li>
        </ul>
      </div>

      <div class="product-preview__frames">
        <div class="browser-frame browser-frame--main">
          <div class="browser-frame__bar">
            <span /><span /><span />
            <em>结构预测 · Mol* 查看器</em>
          </div>
          <div class="mock-viewer">
            <div class="mock-viewer__canvas">
              <div class="mock-protein mock-protein--a" />
              <div class="mock-protein mock-protein--b" />
              <div class="mock-interface" />
            </div>
            <div class="mock-viewer__sidebar">
              <div class="mock-metric"><span>pLDDT</span><strong>82</strong></div>
              <div class="mock-metric"><span>ipTM</span><strong>0.83</strong></div>
              <div class="mock-metric"><span>界面</span><strong>H_A</strong></div>
            </div>
          </div>
        </div>

        <div class="browser-frame browser-frame--float">
          <div class="browser-frame__bar">
            <span /><span /><span />
            <em>Rosetta 结构评价</em>
          </div>
          <div class="mock-table">
            <div class="mock-table__head">
              <span>排名</span><span>突变体</span><span>ΔΔG</span><span>score</span>
            </div>
            <div class="mock-table__row mock-table__row--top">
              <span>1</span><span>S102P</span><span class="good">-5.15</span><span>0.77</span>
            </div>
            <div class="mock-table__row">
              <span>2</span><span>S102A</span><span class="good">-5.32</span><span>0.77</span>
            </div>
            <div class="mock-table__row">
              <span>3</span><span>WT</span><span>0.00</span><span>0.67</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.product-preview {
  padding: 3.5rem 0;
  background: linear-gradient(180deg, #fff 0%, #f0f7f6 100%);
}

.product-preview__grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(300px, 1.05fr);
  gap: 2.5rem;
  align-items: center;

  @media (max-width: 960px) {
    grid-template-columns: 1fr;
  }
}

.product-preview__eyebrow {
  margin: 0 0 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--bio-green-dark);
}

h2 {
  margin: 0;
  font-size: clamp(1.4rem, 2.5vw, 1.9rem);
  line-height: 1.25;
  color: var(--title);
  letter-spacing: -0.03em;
}

.product-preview__copy > p {
  margin: 0.85rem 0 0;
  font-size: 0.92rem;
  line-height: 1.7;
  color: var(--body);
}

.product-preview__copy ul {
  margin: 1.25rem 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  li {
    position: relative;
    padding-left: 1.1rem;
    font-size: 0.86rem;
    color: var(--body);

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0.55rem;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--bio-green);
    }
  }
}

.product-preview__frames {
  position: relative;
  min-height: 340px;
}

.browser-frame {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: #fff;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.12);
}

.browser-frame--main {
  position: relative;
  z-index: 1;
}

.browser-frame--float {
  position: absolute;
  right: -4%;
  bottom: -8%;
  width: 58%;
  z-index: 2;

  @media (max-width: 960px) {
    position: relative;
    right: auto;
    bottom: auto;
    width: 100%;
    margin-top: 1rem;
  }
}

.browser-frame__bar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.55rem 0.75rem;
  background: #f1f5f9;
  border-bottom: 1px solid var(--border);

  span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #cbd5e1;

    &:first-child {
      background: #f87171;
    }
    &:nth-child(2) {
      background: #fbbf24;
    }
    &:nth-child(3) {
      background: #4ade80;
    }
  }

  em {
    margin-left: 0.5rem;
    font-style: normal;
    font-size: 0.68rem;
    color: var(--muted);
  }
}

.mock-viewer {
  display: grid;
  grid-template-columns: 1fr 88px;
  min-height: 220px;
}

.mock-viewer__canvas {
  position: relative;
  background: linear-gradient(145deg, #0f172a, #1e293b);
  overflow: hidden;
}

.mock-protein {
  position: absolute;
  border-radius: 40% 60% 50% 50%;
  opacity: 0.85;
}

.mock-protein--a {
  width: 120px;
  height: 180px;
  top: 18%;
  left: 22%;
  background: linear-gradient(180deg, #34d399, #059669);
  transform: rotate(-12deg);
}

.mock-protein--b {
  width: 100px;
  height: 140px;
  top: 28%;
  left: 48%;
  background: linear-gradient(180deg, #60a5fa, #2563eb);
  transform: rotate(18deg);
}

.mock-interface {
  position: absolute;
  width: 36px;
  height: 36px;
  top: 42%;
  left: 44%;
  border-radius: 50%;
  border: 2px dashed #fbbf24;
  box-shadow: 0 0 20px rgba(251, 191, 36, 0.5);
}

.mock-viewer__sidebar {
  padding: 0.65rem 0.5rem;
  background: #f8fafc;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.mock-metric {
  padding: 0.4rem 0.45rem;
  border-radius: 8px;
  background: #fff;
  border: 1px solid var(--border);

  span {
    display: block;
    font-size: 0.62rem;
    color: var(--muted);
  }

  strong {
    font-size: 0.82rem;
    color: var(--title);
  }
}

.mock-table {
  padding: 0.65rem;
  font-size: 0.72rem;
}

.mock-table__head,
.mock-table__row {
  display: grid;
  grid-template-columns: 36px 1fr 56px 48px;
  gap: 0.35rem;
  padding: 0.35rem 0.25rem;
}

.mock-table__head {
  color: var(--muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}

.mock-table__row {
  color: var(--body);
  border-radius: 6px;

  &--top {
    background: var(--bio-green-light);
    font-weight: 600;
  }
}

.good {
  color: var(--bio-green-dark);
}
</style>
