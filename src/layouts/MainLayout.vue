<!-- src/layouts/MainLayout.vue -->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header
      elevated
      :class="{ 'header-hidden': isChapterPage && !showHeader }"
      class="header-transition"
    >
      <q-toolbar>
        <q-btn flat to="/" icon="menu_book" :label="$q.screen.gt.xs ? $t('nav.home') : undefined" />
        <q-space />

        <!-- Search bar -->
        <q-input
          v-model="searchQuery"
          dense
          standout
          :placeholder="$t('search.placeholder')"
          class="search-input"
          @keyup.enter="performSearch"
        >
          <template v-slot:prepend>
            <q-icon name="search" />
          </template>
          <template v-slot:append>
            <q-icon
              v-if="searchQuery"
              name="close"
              @click="searchQuery = ''"
              class="cursor-pointer"
            />
          </template>
        </q-input>

        <q-space />

        <q-btn flat @click="showDialog({ component: ConfigCard, position: 'bottom' })" icon="settings" :label="$q.screen.gt.xs ? $t('common.settings') : undefined">
          <q-tooltip>{{ $t('settings.title') }}</q-tooltip>
        </q-btn>
        <q-btn v-if="book.allChapters.length" flat round dense icon="menu" @click="drawerRight = !drawerRight">
          <q-tooltip>{{ $t('nav.chapterList') }}</q-tooltip>
        </q-btn>
      </q-toolbar>
    </q-header>

      <q-drawer
        v-if="book.allChapters.length && book.bookId"
        side="right"
        v-model="drawerRight"
        bordered
        :width="250"
        :breakpoint="500"
        behavior="desktop"
      >
        <q-scroll-area class="fit" :key="book.bookId">
          <div class="q-pa-sm">
            <div v-for="(c,index) in book.allChapters" :key="`${book.bookId}-${c.number}`">
              <q-btn dense
                      flat :to="chapterLink(c.number, c.title)"
                      :disable="index === book.getChapterIndex"
                      class="chapter-btn"
                      :class="{ current: index === book.getChapterIndex }"
                      >{{ c.title }}</q-btn>
            </div>
          </div>
        </q-scroll-area>
      </q-drawer>

    <q-page-container>
      <router-view />

      <!-- Header toggle button for chapter page -->
      <q-page-sticky v-if="isChapterPage && !showHeader" position="top" :offset="[0, 10]">
        <q-btn
          round
          color="primary"
          icon="expand_more"
          size="sm"
          @click="showHeader = true"
          class="btn-transparent"
        >
          <q-tooltip>{{ $t('action.showHeader') }}</q-tooltip>
        </q-btn>
      </q-page-sticky>

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
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue';
import { chapterLink, isDarkActive, scrollToWindow } from 'src/services/utils';
import { showDialog } from 'src/services/utils';
import ConfigCard from 'src/components/ConfigCard.vue';
import SearchDialog from 'src/components/SearchDialog.vue';
import { useRoute, useRouter } from 'vue-router';
import { useBookStore } from 'src/stores/books';
import { useQuasar } from 'quasar';

const $q = useQuasar();
const { update } = useAppConfig();
const route = useRoute()
const router = useRouter()
const book = useBookStore()

const showScrollTo = ref({top: false, bottom: false, right: false, left: false,
  topleft: false, topright: false, bottomleft: false, bottomright: false
});

// Header visibility control for chapter page
const isChapterPage = computed(() => route.name === 'Chapter')
const showHeader = ref(true)
let lastScrollY = 0

// Search functionality
const searchQuery = ref('')

function performSearch() {
  if (!searchQuery.value.trim()) return

  console.log('[MainLayout] Performing search for:', searchQuery.value)

  // Show search dialog with results
  showDialog({
    component: SearchDialog,
    componentProps: {
      query: searchQuery.value
    }
  })
}

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

  // Auto-hide/show header on chapter page based on scroll direction
  if (isChapterPage.value) {
    const scrollingUp = y < lastScrollY
    const scrollingDown = y > lastScrollY
    const atTop = y < 100

    if (atTop) {
      showHeader.value = true
    } else if (scrollingUp && y > 100) {
      showHeader.value = true
    } else if (scrollingDown && y > 150) {
      showHeader.value = false
    }

    lastScrollY = y
  }
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

// Watch route changes to reset header visibility
watch(() => route.name, (newRouteName) => {
  if (newRouteName !== 'Chapter') {
    // Always show header on non-chapter pages
    showHeader.value = true
  } else {
    // Start with header visible on chapter page
    showHeader.value = true
    lastScrollY = window.scrollY
  }
})
// const chapter = computed<ChapterRef>(() => JSON.parse(config.value.chapter || '{"number": "1"}'))
// const chapters = computed<ChapterRef[]>(() => 
// {
//   const raw = config.value?.chapters ?? '[]'
//   try {
//     return JSON.parse(raw) as ChapterRef[]
//   } catch {
//     return []
//   }
// })
// const hasChapters = computed(() => chapters.value.length > 0);

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
// watch(chapter, async () => {
//   // Only scroll if drawer is open
//   if (!drawerRight.value) return

//   await nextTick()

//   const el = document.querySelector('.chapter-btn.current')
//   if (el) {
//     el.scrollIntoView({
//       behavior: 'smooth',
//       block: 'center'
//     })
//   }
// })

// Update config.chapter immediately when route changes to Chapter page
watch(() => route.params, (params) => {
  if (route.name === 'Chapter' && params.chapterNum && params.chapterTitle) {
    // Skip if chapters not loaded yet
    if (book.allChapters.length === 0) {
      console.log('[MainLayout] Skipping chapter update - chapters not loaded yet')
      return
    }

    const chapterNum = Number(params.chapterNum)
    const chapterTitle = String(params.chapterTitle)

    // Find the matching chapter in the chapters list (with type-safe comparison)
    const matchingChapter = book.allChapters.find(
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

// const total = computed(() => chapters.value.length)
// const chapterIndex = computed(() => {
//   const index = chapters.value.findIndex(
//     c => Number(c.number) === Number(chapter.value.number) && String(c.title) === String(chapter.value.title)
//   )
//   console.log('[MainLayout] chapter index:', index, 'for chapter:', chapter.value.number, chapter.value.title);
//   return index === -1 ? 0 : index
// })

const navPrev = computed(() => {
  if (!book.prevChapter) return null
  return chapterLink(book.prevChapter.number, book.prevChapter.title)
})

const navNext = computed(() => {
  if (!book.nextChapter) return null
  return chapterLink(book.nextChapter.number, book.nextChapter.title)
})

function nav(pos: 'next' | 'prev') {
  console.log('[MainLayout] nav called:', pos)
  console.log('[MainLayout] current chapter:', book.allChapters[book.getChapterIndex])
  console.log('[MainLayout] chapterIndex:', book.getChapterIndex)
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

/* Header transition and hiding */
.header-transition {
  transition: transform 0.3s ease-in-out;
}

.header-hidden {
  transform: translateY(-100%);
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

/* Mobile optimizations */
@media (max-width: 600px) {
  /* Make drawer full-screen on mobile */
  .q-drawer--right {
    width: 100% !important;
  }

  /* Hide some scroll buttons on mobile to reduce clutter */
  .q-page-sticky:not([position="left"]):not([position="right"]):not([position="bottom"]) {
    display: none !important;
  }

  /* Keep only essential navigation buttons on mobile */
  .q-page-sticky[position="left"],
  .q-page-sticky[position="right"],
  .q-page-sticky[position="bottom"] {
    opacity: 0.8;
  }

  /* Smaller button size on mobile */
  .q-page-sticky .q-btn {
    width: 40px;
    height: 40px;
  }

  /* Adjust header search input on mobile */
  .search-input {
    max-width: 180px !important;
  }

  /* Single-row toolbar on mobile */
  .q-toolbar {
    flex-wrap: nowrap;
  }
}

/* Tablet optimizations */
@media (min-width: 601px) and (max-width: 1024px) {
  /* Medium drawer width on tablet */
  .q-drawer--right {
    width: 300px !important;
  }

  /* Show more scroll buttons on tablet */
  .q-page-sticky {
    opacity: 0.9;
  }
}

/* Large screen optimizations */
@media (min-width: 1025px) {
  /* Default drawer width */
  .q-drawer--right {
    width: 250px;
  }

  /* Full opacity for all buttons on desktop */
  .q-page-sticky {
    opacity: 1;
  }

  /* Larger touch targets for mouse */
  .q-page-sticky .q-btn {
    width: 48px;
    height: 48px;
  }
}
</style>