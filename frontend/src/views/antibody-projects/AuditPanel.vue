<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchAuditEvents, type AuditEvent } from '@/api/antibodyProjects'

const props = defineProps<{ projectId: string }>()
const events = ref<AuditEvent[]>([])
const loading = ref(false)

const actionText: Record<string, string> = {
  create: '创建',
  update: '修改',
  delete: '移除',
  lock: '锁定',
  mark_tested: '标记为已实验',
}
const entityText: Record<string, string> = {
  project: '项目',
  project_member: '项目成员',
  candidate: '候选抗体',
  antibody_version: '序列版本',
  version_mutation: '突变说明',
  sample_batch: '样品批次',
  experiment: '实验记录',
  job_link: '计算任务关联',
  artifact: '附件',
}

async function load() {
  loading.value = true
  try {
    events.value = await fetchAuditEvents(props.projectId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作历史加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-loading="loading" class="page-card audit-card">
    <div class="section-head">
      <div><h2>操作历史</h2><p>修改前后快照按时间留存，不能通过页面编辑</p></div>
      <el-button size="small" @click="load">刷新</el-button>
    </div>
    <el-timeline>
      <el-timeline-item
        v-for="event in events"
        :key="event.id"
        :timestamp="new Date(event.created_at).toLocaleString('zh-CN')"
        placement="top"
      >
        <div class="audit-item">
          <strong>{{ actionText[event.action] || event.action }}{{ entityText[event.entity_type] || event.entity_type }}</strong>
          <span>对象 {{ event.entity_id.slice(0, 8) }} · 操作者 {{ event.actor_id?.slice(0, 8) || '系统' }}</span>
          <el-collapse v-if="event.before_json || event.after_json">
            <el-collapse-item title="查看修改快照">
              <div class="snapshot-grid">
                <div v-if="event.before_json"><label>修改前</label><pre>{{ JSON.stringify(event.before_json, null, 2) }}</pre></div>
                <div v-if="event.after_json"><label>修改后</label><pre>{{ JSON.stringify(event.after_json, null, 2) }}</pre></div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-timeline-item>
    </el-timeline>
    <p v-if="!events.length && !loading" class="empty-note">暂无操作记录</p>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.audit-card { padding: 1rem; }
.audit-item {
  display: grid;
  gap: 0.25rem;
  strong { color: var(--title); }
  > span { color: var(--muted); font-size: 0.74rem; }
}
.snapshot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
.snapshot-grid label { color: var(--muted); font-size: 0.72rem; }
.snapshot-grid pre {
  max-height: 320px;
  overflow: auto;
  margin: 0.25rem 0 0;
  padding: 0.6rem;
  border-radius: 6px;
  background: #f8fafc;
  font-size: 0.68rem;
  white-space: pre-wrap;
}
@media (max-width: 760px) {
  .snapshot-grid { grid-template-columns: 1fr; }
}
</style>
