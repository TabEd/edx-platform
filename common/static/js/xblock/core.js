(function($, JSON) {

    'use strict';

    function initializeBlockLikes(block_class, initializer, element, requestToken) {
        var requestToken = requestToken || $(element).data('request-token');
        if (requestToken) {
            var selector = '.' + block_class + '[data-request-token="' + requestToken + '"]';
        } else {
            var selector = '.' + block_class;
        }
        return $(element).immediateDescendents(selector).map(function(idx, elem) {
            return initializer(elem, requestToken);
        }).toArray();
    }

    function elementRuntime(element) {
        var $element = $(element);
        var runtime = $element.data('runtime-class');
        var version = $element.data('runtime-version');
        var initFnName = $element.data('init');

        if (runtime && version && initFnName) {
            return new window[runtime]['v' + version];
        } else {
            if (!runtime || !version || !initFnName) {
                var elementTag = $('<div>').append($element.clone()).html();
                console.log('Block ' + elementTag + ' is missing data-runtime, data-runtime-version or data-init, and can\'t be initialized');
            }
            return null;
        }
    }

    function initArgs(element) {
        var initargs = $('.xblock_json_init_args', element).text();
        return initargs ? JSON.parse(initargs) : {};
    }

    /**
     * Construct an XBlock family object from an element. The constructor
     * function is loaded from the 'data-init' attribute of the element.
     * The constructor is called with the arguments 'runtime', 'element',
     * and then all of 'block_args'.
     */
    function constructBlock(element, block_args) {
        var block;
        var $element = $(element);
        var initFnName = $element.data('init');
        var runtime = elementRuntime(element);

        block_args.unshift(element);
        block_args.unshift(runtime);

        var initFn = window[initFnName];

        // This create a new constructor that can then apply() the block_args
        // to the initFn.
        function Block() {
            return initFn.apply(this, block_args);
        }
        Block.prototype = initFn.prototype;

        if (runtime) {
            block = new Block();
            block.runtime = runtime;
        } else {
            block = {};
        }
        block.element = element;
        block.name = $element.data('name');
        block.type = $element.data('block-type');
        $element.trigger('xblock-initialized');
        $element.data('initialized', true);
        $element.addClass('xblock-initialized');
        return block;
    }

    var XBlock = {
        Runtime: {},

        /**
         * Initialize the javascript for a single xblock element, and for all of it's
         * xblock children that match requestToken. If requestToken is omitted, use the
         * data-request-token attribute from element, or use the request-tokens specified on
         * the children themselves.
         */
        initializeBlock: function(element, requestToken) {
            var $element = $(element);

            var requestToken = requestToken || $element.data('request-token');
            var children = XBlock.initializeBlocks($element, requestToken);
            $element.prop('xblock_children', children);

            return constructBlock(element, [initArgs(element)]);
        },

        /**
         * Initialize the javascript for a single xblock aside element that matches requestToken.
         * If requestToken is omitted, use the data-request-token attribute from element, or use
         * the request-tokens specified on the children themselves.
         */
        initializeAside: function(element, requestToken) {
            var blockUsageId = $(element).data('block_id');
            var blockElement = $(element).siblings('[data-usage="' + blockUsageId + '"]');
            return constructBlock(element, [blockElement, initArgs(element)]);
        },

        /**
         * Initialize all XBlocks inside element that were rendered with requestToken.
         * If requestToken is omitted, and element has a 'data-request-token' attribute, use that.
         * If neither is available, then use the request tokens of the immediateDescendent xblocks.
         */
        initializeXBlocks: function(element, requestToken) {
            return initializeBlockLikes('xblock', XBlock.initializeBlock, element, requestToken);
        },

        /**
         * Initialize all XBlockAsides inside element that were rendered with requestToken.
         * If requestToken is omitted, and element has a 'data-request-token' attribute, use that.
         * If neither is available, then use the request tokens of the immediateDescendent xblocks.
         */
        initializeXBlockAsides: function(element, requestToken) {
            return initializeBlockLikes('xblock_asides-v1', XBlock.initializeAside, element, requestToken);
        },

        /**
         * Initialize all XBlock-family blocks inside element that were rendered with requestToken.
         * If requestToken is omitted, and element has a 'data-request-token' attribute, use that.
         * If neither is available, then use the request tokens of the immediateDescendent xblocks.
         */
        initializeBlocks: function(element, requestToken) {
            XBlock.initializeXBlocks(element, requestToken);
            return XBlock.initializeXBlockAsides(element, requestToken);
        }
    };

    this.XBlock = XBlock;

}).call(this, $, JSON);