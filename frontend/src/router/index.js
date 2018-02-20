import Vue from 'vue';
import Router from 'vue-router';
import Radar from '@/components/Radar';

Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/radar',
      name: 'Radar',
      component: Radar,
    },
  ],
});
