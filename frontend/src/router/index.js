import Vue from 'vue';
import Router from 'vue-router';

import Library from '@/components/Library';
import Radar from '@/components/Radar';
import Tracked from '@/components/Tracked';

Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/radar',
      name: 'Radar',
      component: Radar,
    },
    {
      path: '/library',
      name: 'Library',
      component: Library,
    },
    {
      path: '/tracked',
      name: 'Tracked',
      component: Tracked,
    },
  ],
});
