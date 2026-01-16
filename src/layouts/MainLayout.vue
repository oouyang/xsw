<!-- src/layouts/MainLayout.vue -->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat to="/" icon="menu_book" />
        <q-space />
        <q-btn flat @click="toggleDark()" :label="$q.dark.isActive ? '🌕' : '🖤'" />
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
      <q-page-sticky v-if="showScrollTo.right" @click="scrollTo('right')" position="right" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_upward" class="rotate-90" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.left" @click="scrollTo('left')" position="left" :offset="[18, 0]">
        <q-btn round color="accent" icon="arrow_back" />
      </q-page-sticky>
      <q-page-sticky v-if="showScrollTo.bottomleft" @click="scrollTo('bottomleft')" position="bottom-left" :offset="[18, 18]">
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
import { useQuasar } from 'quasar';
import { useAppConfig } from 'src/services/useAppConfig';
import { scrollToWindow } from 'src/services/utils';
import type { ChapterRef } from 'src/types/book-api';
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue';

const { config } = useAppConfig();

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
});

onBeforeUnmount(() => {
  window.removeEventListener('scroll', handleScroll);
});

const $q = useQuasar();
let dark = $q.localStorage.getItem('dark') === true
$q.dark.set(dark)
function toggleDark() {
  dark = !dark
  $q.localStorage.setItem('dark', dark)
  $q.dark.set(dark)
}
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

function chapterLink(num: number, title: string) {
  return {
    name: 'Chapter',
    params: { bookId: config.value.bookId, chapterNum: Number(num), chapterTitle: title },
  };
}

watch(drawerRight, async (open) => {
  if (!open) return

  await nextTick()

  const el = document.querySelector('.chapter-btn.current')
  if (el) {
    el.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })
    console.log('scroll to ', chapter);
  }
})

</script>
