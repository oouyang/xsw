import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'Dashboard', component: () => import('pages/DashboardPage.vue') },
      {
        path: 'cate/:catId',
        name: 'Category',
        component: () => import('pages/CategoryPage.vue'),
        props: true,
      },
      {
        path: 'book/:bookId/chapters',
        name: 'Chapters',
        component: () => import('pages/ChaptersPage.vue'),
        props: true,
      },
      {
        path: 'book/:bookId/chapter/:chapterId/:chapterTitle?',
        name: 'Chapter',
        component: () => import('pages/ChapterPage.vue'),
        props: route => ({
            bookId: route.params.bookId,
            chapterId: String(route.params.chapterId),
            chapterTitle: route.params.chapterTitle
          }),
      },
      {
        path: 'auth/wechat/callback',
        name: 'WeChatCallback',
        component: () => import('pages/WeChatCallbackPage.vue'),
      },
    ],
  },
  { path: '/:catchAll(.*)*', component: () => import('pages/ErrorNotFound.vue') },
];

export default routes;
