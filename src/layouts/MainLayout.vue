<!-- src/layouts/MainLayout.vue -->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat to="/" icon="menu_book" />
        <q-space />
        <q-btn flat @click="showDialog({ component: ConfigCard, position: 'bottom' }).hide()" icon="settings" />
        <q-btn v-if="false" flat to="/" icon="dashboard" label="🏛️" />
        <q-btn v-else flat round dense icon="menu" @click="drawerRight = !drawerRight" />
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
        <q-btn round color="accent" icon="arrow_back" class="rotate-45" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.top" position="top" :offset="[0, 18]">
        <q-btn round color="accent" icon="arrow_back" @click="scrollTo('top')" class="rotate-90" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.topright" @click="scrollTo('topright')" position="top-right" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_upward" class="rotate-45" />
      </q-page-sticky>
      <q-page-sticky v-if="route.name === 'Chapter' && chapter.number !== chapters.length + 1" @click="nav('next')" position="right" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_upward" class="rotate-90" />
      </q-page-sticky>
      <q-page-sticky v-if="route.name === 'Chapter' && chapter.number !== 1" @click="nav('prev')" position="left" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_back" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottomleft" @click="scrollTo('bottomleft')"  position="bottom-left" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-135" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottom" @click="scrollTo('bottom')" position="bottom" :offset="[0, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-90" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottomright" @click="scrollTo('bottomright')" position="bottom-right" :offset="[18, 18]">
        <q-btn round color="accent" icon="arrow_forward" class="rotate-45" />
      </q-page-sticky>
    </q-page-container>
  </q-layout>

</template>
<script setup lang="ts">
import { useAppConfig } from 'src/services/useAppConfig';
import type { ChapterRef } from 'src/types/book-api';
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue';
import { chapterLink, scrollToWindow, setDark } from 'src/services/utils';
import { showDialog } from 'src/services/utils';
import ConfigCard from 'src/components/ConfigCard.vue';
import { useRoute, useRouter } from 'vue-router';

const { config } = useAppConfig();
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
  if (config.value.dark === 'true') {
    setDark(true);
  } else {
    setDark(false);
  }
  
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

watch(drawerRight, async (open) => {
  if (!open) return

  await nextTick()

  const el = document.querySelector('.chapter-btn.current')
  if (el) {
    el.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })
    // console.log('scroll to ', chapter);
  }
})

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
const chapterIndex = computed(() => chapters.value.findIndex(
      c => c.number === chapter.value.number && c.title == chapter.value.title
    ) || 0)

const navPrev = computed(() => {
  if (!chapter.value || total.value === 0) return null
  const index = Math.max(0, chapterIndex.value - 1)
  // 1-based → array index (0-based)
  const title = chapters.value[index - 1]?.title ?? ''
  return chapterLink(index, title)
})

const navNext = computed(() => {
  if (!chapter.value || total.value === 0) return null
  const index = Math.min(chapterIndex.value + 1, total.value-1)
  const title = chapters.value[index]?.title ?? ''
  return chapterLink(chapters.value[index]?.number || 1, title)
})

function nav(pos: 'next' | 'prev') {
  console.debug('[nav] destination for', pos, chapter.value, chapters.value)
  if (pos === 'next' && navNext.value) {
    void router.push(navNext.value)
    return
  }
  if (pos === 'prev' && navPrev.value) {
    void router.push(navPrev.value)
    return
  }
  
  // Optional: fallback (no-op at boundaries)
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
