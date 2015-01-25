module.exports = function(grunt) {
    grunt.loadNpmTasks('grunt-bowercopy');
    grunt.initConfig({
        bowercopy: {
            options: {clean: true},
            js: {
                options: {destPrefix: 'great/static/js/vendor'},
                files: {
                    'backbone.paginator.js': 'backbone.paginator/lib/backbone.paginator.js'
                }
            }
        }
    });
}
