<!-- src/layouts/MainLayout.vue -->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat to="/" icon="menu_book" />
        <q-space />
        <q-btn flat @click="toggleDark()" :label="$q.dark.isActive ? '🌕' : '🖤'" />
        <q-btn flat to="/" icon="dashboard" label="🏛️" />
      </q-toolbar>
    </q-header>
    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
  
  <!-- <q-page-sticky position="bottom-right" :offset="[18, 18]" v-show="showScrollTop">
    <q-btn
      round
      color="primary"
      icon="keyboard_arrow_up"
      @click="scrollToTop"
      title="Back to Top"
    />
  </q-page-sticky> -->
</template>
<script setup lang="ts">
import { useQuasar } from 'quasar';
// import { ref, onMounted, onBeforeUnmount } from 'vue';

// const showScrollTop = ref(false);

// function handleScroll() {
//   showScrollTop.value = true; //window.scrollY > 200;
// }

// function scrollToTop() {
//   window.scrollTo({ top: 0, behavior: 'smooth' });
// }

// onMounted(() => {
//   window.addEventListener('scroll', handleScroll);
// });

// onBeforeUnmount(() => {
//   window.removeEventListener('scroll', handleScroll);
// });

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
</script>
<!-- <template>
  <q-layout view="lHh Lpr lFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" @click="toggleLeftDrawer" />

        <q-toolbar-title> Quasar App </q-toolbar-title>

        <div>Quasar v{{ $q.version }}</div>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered>
      <q-list>
        <q-item-label header> Essential Links </q-item-label>

        <EssentialLink v-for="link in linksList" :key="link.title" v-bind="link" />
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import EssentialLink, { type EssentialLinkProps } from 'components/EssentialLink.vue';

const linksList: EssentialLinkProps[] = [
  {
    title: 'Docs',
    caption: 'quasar.dev',
    icon: 'school',
    link: 'https://quasar.dev',
  },
  {
    title: 'Github',
    caption: 'github.com/quasarframework',
    icon: 'code',
    link: 'https://github.com/quasarframework',
  },
  {
    title: 'Discord Chat Channel',
    caption: 'chat.quasar.dev',
    icon: 'chat',
    link: 'https://chat.quasar.dev',
  },
  {
    title: 'Forum',
    caption: 'forum.quasar.dev',
    icon: 'record_voice_over',
    link: 'https://forum.quasar.dev',
  },
  {
    title: 'Twitter',
    caption: '@quasarframework',
    icon: 'rss_feed',
    link: 'https://twitter.quasar.dev',
  },
  {
    title: 'Facebook',
    caption: '@QuasarFramework',
    icon: 'public',
    link: 'https://facebook.quasar.dev',
  },
  {
    title: 'Quasar Awesome',
    caption: 'Community Quasar projects',
    icon: 'favorite',
    link: 'https://awesome.quasar.dev',
  },
];

const leftDrawerOpen = ref(false);

function toggleLeftDrawer() {
  leftDrawerOpen.value = !leftDrawerOpen.value;
}
</script> -->
