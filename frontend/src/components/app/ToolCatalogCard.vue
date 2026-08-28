<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  TOOL_FUNCTION_LABELS,
  TOOL_MODALITY_LABELS,
  type PlatformTool,
} from '@/config/tools'

const props = defineProps<{ tool: PlatformTool }>()
const router = useRouter()

const visibleTags = computed(() => {
  const tags = [
    TOOL_FUNCTION_LABELS[props.tool.function],
    ...props.tool.modalities.slice(0, 2).map((m) => TOOL_MODALITY_LABELS[m]),
  ]
  const extra = props.tool.modalities.length - 2
  if (extra > 0) tags.push(`+${extra}`)
  return tags
})

function open() {
  router.push(props.tool.route)
}
</script>

<template>
  <article class="tool-card" @click="open">
    <div class="tool-card__tags">
      <span v-if="tool.isNew" class="tool-card__new">New</span>
      <span v-for="tag in visibleTags" :key="tag" class="tool-card__tag">{{ tag }}</span>
    </div>
    <h3 class="tool-card__name">{{ tool.name }}</h3>
    <p class="tool-card__desc">{{ tool.description }}</p>
    <p v-if="tool.citation" class="tool-card__cite">{{ tool.citation }}</p>
    <footer class="tool-card__foot">
      <span class="tool-card__duration">{{ tool.duration }}</span>
      <button type="button" class="tool-card__cta" @click.stop="open">
        开始使用
        <el-icon><ArrowRight /></el-icon>
      </button>
    </footer>
  </article>
</template>

<style scoped lang="scss">
.tool-card {
  display: flex;
  flex-direction: column;
  min-height: 220px;
  padding: 1.15rem 1.2rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;

  &:hover {
    border-color: #d1d5db;
    box-shadow: 0 8px 28px rgba(15, 23, 42, 0.07);
    transform: translateY(-2px);
  }
}

.tool-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.tool-card__new {
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #fff;
  background: #111827;
}

.tool-card__tag {
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 600;
  color: #4b5563;
  background: #f3f4f6;
}

.tool-card__name {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #111827;
}

.tool-card__desc {
  flex: 1;
  margin: 0.55rem 0 0;
  font-size: 0.84rem;
  line-height: 1.6;
  color: #6b7280;
}

.tool-card__cite {
  margin: 0.45rem 0 0;
  font-size: 0.72rem;
  color: #9ca3af;
}

.tool-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1rem;
  padding-top: 0.85rem;
  border-top: 1px solid #f3f4f6;
}

.tool-card__duration {
  font-size: 0.72rem;
  font-weight: 600;
  color: #9ca3af;
}

.tool-card__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 0.78rem;
  font-weight: 700;
  color: #111827;
  cursor: pointer;

  .tool-card:hover & {
    color: #0d9488;
  }
}
</style>
