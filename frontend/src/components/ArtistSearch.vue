<template>
  <div class="uk-modal-dialog uk-flex uk-flex-center uk-flex-middle" uk-height-viewport>
    <button class="uk-modal-close-full" type="button" uk-close></button>
    <form class="uk-search uk-search-large">
      <input
      class="uk-search-input uk-text-center"
      type="Artist"
      placeholder="Add Artist..."
      autofocus>
    </form>
  </div>
</template>

<script>
export default {
  name: 'ArtistSearch',
};
</script>
