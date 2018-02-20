import Vue from 'vue';
import Router from 'vue-router';

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
      path: '/tracked',
      name: 'Tracked',
      component: Tracked,
    },
  ],
});
