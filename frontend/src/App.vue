<template>
  <div id="app">
    <Navbar></Navbar>
    <div class="uk-section uk-section-default">
      <router-view></router-view>
    </div>
  </div>
</template>

<script>
import UIkit from 'uikit';
import Icons from 'uikit/dist/js/uikit-icons';

import Navbar from '@/components/Navbar';

UIkit.use(Icons);

export default {
  name: 'App',
  components: { Navbar },
};
</script>

<style lang="less" src="uikit/src/less/uikit.theme.less">
</style>
