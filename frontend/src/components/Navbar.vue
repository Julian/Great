<template>
  <nav class="uk-navbar-container" uk-navbar>
    <div class="uk-navbar-center">
      <ul class="uk-navbar-nav">
        <li><router-link to="{ name: 'library' }">Library</router-link></li>
        <li><router-link to="{ name: 'radar' }">Radar</router-link></li>
        <li><router-link to="{ name: 'tracked' }">Tracked</router-link></li>
      </ul>
    </div>
  </nav>
</template>

<script>
export default {
  name: 'Navbar',
};
</script>
