import Vue from 'vue';
import Router from 'vue-router';

import Library from '@/components/Library';
import Radar from '@/components/Radar';
import Tracked from '@/components/Tracked';

Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/',
      name: 'library',
      component: Library,
    },
    {
      path: '/radar',
      name: 'radar',
      component: Radar,
    },
    {
      path: '/tracked',
      name: 'tracked',
      component: Tracked,
    },
  ],
});
