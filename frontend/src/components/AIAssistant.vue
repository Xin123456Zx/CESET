<template>
  <!-- Floating button in the bottom-right corner -->
  <div
    class="fixed bottom-6 right-6 z-[2000] w-[56px] h-[56px] rounded-full bg-[#ACACFF] border-2 border-white shadow-lg
           flex items-center justify-center cursor-pointer select-none hover:scale-105 transition-transform"
    @click="open = true"
    title="AI Assistant"
  >
    <span class="text-white font-bold text-[16px]">AI</span>
  </div>

  <el-drawer v-model="open" :with-header="false" size="440px" class="!bg-white">
    <div class="flex flex-col h-full">
      <!-- Header -->
      <div class="flex items-center justify-between p-3 rounded-[6px] bg-[#ACACFF] border border-[#7F7F7F]">
        <h2 class="text-lg font-semibold text-white">AI Assistant</h2>
        <span class="text-white text-[12px] bg-[#8b8bef] rounded-full px-2 py-0.5">
          {{ statusText }}
        </span>
      </div>

      <!-- Message area -->
      <div ref="msgBox" class="flex-1 overflow-y-auto py-3 space-y-3">
        <div v-if="!messages.length" class="text-gray-400 text-[13px] px-2 leading-6">
          Ask me anything, e.g.:<br/>
          <div v-for="q in exampleQuestions" :key="q"
               class="cursor-pointer hover:text-[#FFAF95]"
               title="Click to ask"
               @click="askExample(q)">· {{ q }}</div>
          <span class="text-gray-300">(Knowledge base: {{ kbDocs.join(', ') || 'loading…' }})</span>
        </div>

        <div v-for="(m, i) in messages" :key="i" class="px-1">
          <!-- User -->
          <div v-if="m.role === 'user'" class="flex justify-end">
            <div class="max-w-[85%] bg-[#FFAF95] text-white rounded-[12px] rounded-br-[2px] px-3 py-2 text-[14px] whitespace-pre-wrap">{{ m.content }}</div>
          </div>
          <!-- Assistant -->
          <div v-else class="flex flex-col items-start">
            <div class="max-w-[92%] bg-[#f2f2fb] text-[#191919] rounded-[12px] rounded-bl-[2px] px-3 py-2 text-[14px] whitespace-pre-wrap leading-6">{{ m.content }}</div>
            <el-collapse v-if="m.sources && m.sources.length" class="w-[92%] !border-0 mt-1">
              <el-collapse-item :title="`References (${m.sources.length})`" class="[&_.el-collapse-item__header]:!text-[12px] [&_.el-collapse-item__header]:!text-gray-400 [&_.el-collapse-item__header]:!h-[26px]">
                <div v-for="s in m.sources" :key="s.index" class="text-[12px] text-gray-500 mb-2">
                  <span class="font-semibold">[{{ s.index }}] {{ s.doc }}</span>
                  <div class="line-clamp-3">{{ s.text }}</div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="sending" class="px-2 text-gray-400 text-[13px]">Thinking…</div>
      </div>

      <!-- Input area -->
      <div class="flex items-end gap-2 pt-2 border-t border-gray-200">
        <el-input
          v-model="draft"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="Ask something… (Enter to send, Shift+Enter for a new line)"
          @keydown.enter.exact.prevent="send"
        />
        <el-button
          type="primary"
          :loading="sending"
          class="!bg-[#FFAF95] !border-white !rounded-[16px]"
          @click="send"
        >Send</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { aiChatApi, aiStatusApi } from '@/api'
import { paramsUsecontext } from '@/contexts/paramsContext'

// Extra UI state from the host page (e.g. Module 3's ROI / recommendation results), merged into app_state with every question
const props = defineProps<{ extraState?: () => Record<string, any> }>()

const open = ref(false)
const draft = ref('')
const sending = ref(false)
const messages = ref<any[]>([])
const msgBox = ref<HTMLDivElement>()

// AI backend status (provider / model / knowledge base)
const provider = ref<string | null>(null)
const model = ref<string | null>(null)
const kbDocs = ref<string[]>([])
const statusText = computed(() =>
  provider.value ? `${provider.value}:${model.value}` : 'retrieval mode (no API key)')

onMounted(async () => {
  try {
    const { data }: any = await aiStatusApi.query({})
    provider.value = data.provider
    model.value = data.model
    kbDocs.value = data.kb_docs || []
  } catch (e) { /* stay silent when the backend is down */ }
})

// App state: watch the parameter context and accumulate this session's submission history, sent to the
// backend with every question, so the AI can answer things like "what are the parameters in row N /
// why does the interval look like this". To expose more UI state to the AI later
// (current confidence, calibration level, etc.), add it to this object.
const ctx = paramsUsecontext()
const history = ref<any[]>([])
watch(() => ctx.value, (n: any) => {
  if (n && n.data && n.data.type === 'nyx' && n.data.data) {
    history.value.push({ ...n.data.data })
  }
})
const appState = () => ({
  dataset: 'nyx',
  history_records: history.value,
  ...(props.extraState ? props.extraState() : {}),
})

// Default questions for the empty state: click to ask
const exampleQuestions = [
  'How does "Recommend Parameters" work in the Para-space view?',
  'What is the relationship between render and calibration in this tool?',
  'What is the non-conformity score in the paper?',
  'What is the difference between aleatoric and epistemic uncertainty?',
]
const askExample = (q: string) => {
  draft.value = q
  send()
}

const scrollBottom = () => nextTick(() => {
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
})

const send = async () => {
  const q = draft.value.trim()
  if (!q || sending.value) return
  draft.value = ''
  messages.value.push({ role: 'user', content: q })
  scrollBottom()
  sending.value = true
  try {
    const { data }: any = await aiChatApi.create({
      data: {
        messages: messages.value.map(m => ({ role: m.role, content: m.content })),
        app_state: appState(),
      },
    })
    messages.value.push({ role: 'assistant', content: data.answer, sources: data.sources })
    provider.value = data.provider
  } catch (err: any) {
    messages.value.push({ role: 'assistant', content: 'AI request failed: ' + err })
  } finally {
    sending.value = false
    scrollBottom()
  }
}
</script>

<style scoped>
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
