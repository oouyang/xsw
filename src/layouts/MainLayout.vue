<!-- src/layouts/MainLayout.vue -->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat to="/" icon="menu_book" :label="$t('nav.home')" />
        <q-space />
        <q-btn flat @click="showDialog({ component: ConfigCard, position: 'bottom' })" icon="settings" :label="$t('common.settings')">
          <q-tooltip>{{ $t('settings.title') }}</q-tooltip>
        </q-btn>
        <q-btn v-if="hasChapters" flat round dense icon="menu" @click="drawerRight = !drawerRight">
          <q-tooltip>{{ $t('nav.chapterList') }}</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

      <q-drawer
        v-if="hasChapters"
        side="right"
        v-model="drawerRight"
        bordered
        :width="250"
        :breakpoint="500"
        behavior="desktop"
      >
        <q-scroll-area class="fit">
          <div class="q-pa-sm">
            <div v-for="c in chapters" :key="c.title">
              <q-btn dense 
                      flat :to="chapterLink(c.number, c.title)"
                      :disable="c.number === chapter.number"
                      class="chapter-btn"
                      :class="{ current: c.number === chapter.number }"
                      >{{ c.title }}</q-btn>
            </div>
          </div>
        </q-scroll-area>
      </q-drawer>

    <q-page-container>
      <router-view />

      <!-- place QPageSticky at end of page -->
      <q-page-sticky v-if="showScrollTo.topleft" @click="scrollTo('topleft')" position="top-left" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_back" class="rotate-45 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.top" position="top" :offset="[0, 18]">
        <q-btn round color="accent" icon="arrow_back" @click="scrollTo('top')" class="rotate-90 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.topright" @click="scrollTo('topright')" position="top-right" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_upward" class="rotate-45 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="route.name === 'Chapter' && navNext" @click="nav('next')" position="right" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_upward" class="rotate-90 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="route.name === 'Chapter' && navPrev" @click="nav('prev')" position="left" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_back" class="btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottomleft" @click="scrollTo('bottomleft')"  position="bottom-left" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-135 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottom" @click="scrollTo('bottom')" position="bottom" :offset="[0, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-90 btn-transparent" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottomright" @click="scrollTo('bottomright')" position="bottom-right" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-45 btn-transparent" />
      </q-page-sticky>
    </q-page-container>
  </q-layout>

</template>
<script setup lang="ts">
import { useAppConfig } from 'src/services/useAppConfig';
import type { ChapterRef } from 'src/types/book-api';
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue';
import { chapterLink, isDarkActive, scrollToWindow } from 'src/services/utils';
import { showDialog } from 'src/services/utils';
import ConfigCard from 'src/components/ConfigCard.vue';
import { useRoute, useRouter } from 'vue-router';

const { config, update } = useAppConfig();
const route = useRoute()
const router = useRouter()

const showScrollTo = ref({top: false, bottom: false, right: false, left: false,
  topleft: false, topright: false, bottomleft: false, bottomright: false
});

function handleScroll() {
  const x = window.scrollX
  const y = window.scrollY

  const maxX = document.documentElement.scrollWidth  - window.innerWidth
  const maxY = document.documentElement.scrollHeight - window.innerHeight

  const threshold = 200 // 可調整

  showScrollTo.value.top         = y > threshold
  showScrollTo.value.bottom      = y < maxY - threshold
  showScrollTo.value.left        = x > threshold
  showScrollTo.value.right       = x < maxX - threshold

  // corner positions = combination of two axes
  showScrollTo.value.topleft     = showScrollTo.value.top    && showScrollTo.value.left
  showScrollTo.value.topright    = showScrollTo.value.top    && showScrollTo.value.right
  showScrollTo.value.bottomleft  = showScrollTo.value.bottom && showScrollTo.value.left
  showScrollTo.value.bottomright = showScrollTo.value.bottom && showScrollTo.value.right
}

function scrollTo(pos: string = 'TOP') {
    // window.scrollTo({ top: 0, behavior: 'smooth' });
    scrollToWindow(pos.toLowerCase())
    console.log('scroll to ', pos);
}
onMounted(() => {
  window.addEventListener('scroll', handleScroll);
  console.log('dark', isDarkActive())

  window.addEventListener('keydown', handleKey)

  console.log('route to chapter', route.name === 'Chapter', route.name)
});

onBeforeUnmount(() => {
  window.removeEventListener('scroll', handleScroll);
  window.removeEventListener('keydown', handleKey)
});

const url = process.env.API_BASE_URL;
console.log('url', url);

const drawerRight = ref(false)
const chapter = computed<ChapterRef>(() => JSON.parse(config.value.chapter || '{"number": "1"}'))
const chapters = computed<ChapterRef[]>(() => 
{
  const raw = config.value?.chapters ?? '[]'
  try {
    return JSON.parse(raw) as ChapterRef[]
  } catch {
    return []
  }
})
const hasChapters = computed(() => chapters.value.length > 0);

// Scroll to current chapter in drawer when drawer opens
watch(drawerRight, async (open) => {
  if (!open) return

  await nextTick()

  const el = document.querySelector('.chapter-btn.current')
  if (el) {
    el.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })
  }
})

// Scroll to current chapter when chapter changes (while drawer is open)
watch(chapter, async () => {
  // Only scroll if drawer is open
  if (!drawerRight.value) return

  await nextTick()

  const el = document.querySelector('.chapter-btn.current')
  if (el) {
    el.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })
  }
})

// Update config.chapter immediately when route changes to Chapter page
watch(() => route.params, (params) => {
  if (route.name === 'Chapter' && params.chapterNum && params.chapterTitle) {
    // Skip if chapters not loaded yet
    if (chapters.value.length === 0) {
      console.log('[MainLayout] Skipping chapter update - chapters not loaded yet')
      return
    }

    const chapterNum = Number(params.chapterNum)
    const chapterTitle = String(params.chapterTitle)

    // Find the matching chapter in the chapters list (with type-safe comparison)
    const matchingChapter = chapters.value.find(
      c => Number(c.number) === chapterNum && String(c.title) === chapterTitle
    )

    if (matchingChapter) {
      // Update config immediately so MainLayout sees the change
      update({ chapter: JSON.stringify(matchingChapter) })
      console.log('[MainLayout] Updated chapter from route:', matchingChapter)
    } else {
      console.warn('[MainLayout] Chapter not found in list:', chapterNum, chapterTitle)
    }
  }
}, { immediate: true, deep: true })

// const navPrev = computed(() => {
//   const num = Math.max(1, chapter.value.number - 1);
//   return chapterLink(num, chapters.value[num]?.title || '')
// });
// const navNext = computed(() => {
//   const num = Math.min(chapter.value.number + 1, chapters.value.length);
//   return chapterLink(num, chapters.value[num]?.title || '')
// });

// function nav(pos:'next'|'prev') {
//   if (pos === 'next') {
//     router.push(naveNext);
//   }
//   if (pos === 'prev') {
//     router.push(navPrev);
//   }
// }

const total = computed(() => chapters.value.length)
const chapterIndex = computed(() => {
  const index = chapters.value.findIndex(
    c => Number(c.number) === Number(chapter.value.number) && String(c.title) === String(chapter.value.title)
  )
  console.log('[MainLayout] chapter index:', index, 'for chapter:', chapter.value.number, chapter.value.title);
  return index === -1 ? 0 : index
})

const navPrev = computed(() => {
  if (!chapter.value || total.value === 0) return null
  const prevIndex = chapterIndex.value - 1
  if (prevIndex < 0) return null
  const prevChapter = chapters.value[prevIndex]
  if (!prevChapter) return null
  return chapterLink(prevChapter.number, prevChapter.title)
})

const navNext = computed(() => {
  if (!chapter.value || total.value === 0) return null
  const nextIndex = chapterIndex.value + 1
  if (nextIndex >= total.value) return null
  const nextChapter = chapters.value[nextIndex]
  if (!nextChapter) return null
  return chapterLink(nextChapter.number, nextChapter.title)
})

function nav(pos: 'next' | 'prev') {
  console.log('[MainLayout] nav called:', pos)
  console.log('[MainLayout] current chapter:', chapter.value)
  console.log('[MainLayout] chapterIndex:', chapterIndex.value)
  console.log('[MainLayout] navNext:', navNext.value)
  console.log('[MainLayout] navPrev:', navPrev.value)

  if (pos === 'next' && navNext.value) {
    console.log('[MainLayout] Navigating to next:', navNext.value)
    void router.push(navNext.value)
    return
  }
  if (pos === 'prev' && navPrev.value) {
    console.log('[MainLayout] Navigating to prev:', navPrev.value)
    void router.push(navPrev.value)
    return
  }

  console.warn('[MainLayout] Navigation blocked - at boundary or no valid target')
}

function handleKey(e: KeyboardEvent) {
  if (route.name === 'Chapter') {
    if (e.key === 'ArrowRight') {
      nav('next')
    }
    if (e.key === 'ArrowLeft') {
      nav('prev')
    }
  }
}

</script>

<style>
.btn-transparent {
  background-color: rgba(0, 0, 0, 0.2) !important;
}

.chapter-btn {
  width: 100%;
  justify-content: flex-start;
  text-align: left;
  padding: 8px 12px;
  margin: 2px 0;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.chapter-btn:hover {
  background-color: rgba(var(--q-primary), 0.1);
}

.chapter-btn.current {
  background-color: rgba(var(--q-primary), 0.15);
  font-weight: 500;
  color: var(--q-primary);
  border-left: 3px solid var(--q-primary);
}
</style>