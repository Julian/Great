<template>
  <div id="app">
    <router-view/>
  </div>
</template>

<script>
import UIkit from 'uikit';
import Icons from 'uikit/dist/js/uikit-icons';

UIkit.use(Icons);

export default {
  name: 'App',
};
</script>

<style lang="less">
@import "../node_modules/uikit/src/less/uikit.theme.less";
</style>
