module.exports = function(grunt) {
    grunt.loadNpmTasks('grunt-bowercopy');
    grunt.initConfig({
        bowercopy: {
            options: {clean: true},
            css: {
                options: {destPrefix: 'great/static/css/vendor'},
                files: {
                    'backgrid.min.css': 'backgrid/lib/backgrid.min.css'
                }
            },
            js: {
                options: {destPrefix: 'great/static/js/vendor'},
                files: {
                    'backbone.paginator.min.js': 'backbone.paginator/lib/backbone.paginator.min.js',
                    'backgrid.min.js': 'backgrid/lib/backgrid.min.js'
                }
            }
        }
    });
}
