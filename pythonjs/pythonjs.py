#!/usr/bin/env python
# PythonJS to JavaScript Translator
# by Amirouche Boubekki and Brett Hartshorn - copyright 2013
# License: "New BSD"


import sys
from types import GeneratorType

import ast
from ast import Str
from ast import Name
from ast import Tuple
from ast import parse
from ast import Attribute
from ast import NodeVisitor


class JSGenerator(NodeVisitor):
	def __init__(self):
		self._indent = 0
		self._global_funcions = {}
		self._function_stack = []

	def indent(self): return '  ' * self._indent
	def push(self): self._indent += 1
	def pull(self):
		if self._indent > 0: self._indent -= 1

	def visit_In(self, node):
		return ' in '

	def visit_AugAssign(self, node):
		a = '%s %s= %s;' %(self.visit(node.target), self.visit(node.op), self.visit(node.value))
		return a

	def visit_Module(self, node):
		lines = []
		for b in node.body:
			line = self.visit(b)
			if line: lines.append( line )
			else:raise b
		return '\n'.join(lines)

	def visit_Tuple(self, node):
		return '[%s]' % ', '.join(map(self.visit, node.elts))

	def visit_List(self, node):
		return '[%s]' % ', '.join(map(self.visit, node.elts))

	def visit_TryExcept(self, node):
		out = []
		out.append( self.indent() + 'try {' )
		self.push()
		out.extend(
			list( map(self.visit, node.body) )
		)
		self.pull()
		out.append( self.indent() + '} catch(__exception__) {' )
		self.push()
		out.extend(
			list( map(self.visit, node.handlers) )
		)
		self.pull()
		out.append( '}' )
		return '\n'.join( out )

	def visit_Raise(self, node):
		return 'throw %s;' % self.visit(node.type)

	def visit_Yield(self, node):
		return 'yield %s' % self.visit(node.value)

	def visit_ImportFrom(self, node):
		# print node.module
		# print node.names[0].name
		# print node.level
		return ''

	def visit_ExceptHandler(self, node):
		out = ''
		if node.type:
			out = 'if (__exception__ == %s || isinstance([__exception__, %s], Object())) {\n' % (self.visit(node.type), self.visit(node.type))
		if node.name:
			out += 'var %s = __exception__;\n' % self.visit(node.name)
		out += '\n'.join(map(self.visit, node.body)) + '\n'
		if node.type:
			out += '}\n'
		return out

	def visit_Lambda(self, node):
		args = [self.visit(a) for a in node.args.args]
		return '(function (%s) {return %s})' %(','.join(args), self.visit(node.body))



	def visit_FunctionDef(self, node):
		self._function_stack.append( node )
		node._local_vars = set()
		buffer = self._visit_function( node )

		if node == self._function_stack[0]:  ## could do something special here with global function
			#buffer += 'pythonjs.%s = %s' %(node.name, node.name)  ## this is no longer needed
			self._global_funcions[ node.name ] = buffer

		self._function_stack.pop()
		return buffer

	def _visit_function(self, node):
		args = self.visit(node.args)
		if len(node.decorator_list):
			assert len(node.decorator_list)==1
			dec = self.visit(node.decorator_list[0])
			buffer = self.indent() + '%s.%s = function(%s) {\n' % (dec,node.name, ', '.join(args))
		elif len(self._function_stack) == 1:
			## this style will not make function global to the eval context in NodeJS ##
			#buffer = self.indent() + 'function %s(%s) {\n' % (node.name, ', '.join(args))
			## this is required for eval to be able to work in NodeJS, note there is no var keyword.
			buffer = self.indent() + '%s = function(%s) {\n' % (node.name, ', '.join(args))
		else:
			buffer = self.indent() + 'var %s = function(%s) {\n' % (node.name, ', '.join(args))
		self.push()
		body = list()
		for child in node.body:
			if isinstance(child, Str):
				continue

			if isinstance(child, GeneratorType):  ## not tested
				for sub in child:
					body.append( self.indent()+self.visit(sub))
			else:
				body.append( self.indent()+self.visit(child))

		buffer += '\n'.join(body)
		self.pull()
		buffer += '\n%s}\n' %self.indent()
		return buffer

	def _visit_subscript_ellipsis(self, node):
		name = self.visit(node.value)
		return '%s["$wrapped"]' %name


	def visit_Subscript(self, node):
		if isinstance(node.slice, ast.Ellipsis):
			return self._visit_subscript_ellipsis( node )
		else:
			return '%s[%s]' % (self.visit(node.value), self.visit(node.slice))

	def visit_Index(self, node):
		return self.visit(node.value)

	def visit_Slice(self, node):
		raise SyntaxError  ## slicing not allowed here at js level

	def visit_arguments(self, node):
		out = []
		for name in [self.visit(arg) for arg in node.args]:
			out.append(name)
		return out

	def visit_Name(self, node):
		if node.id == 'None':
			return 'undefined'
		elif node.id == 'True':
			return 'true'
		elif node.id == 'False':
			return 'false'
		elif node.id == 'null':
			return 'null'
		return node.id

	def visit_Attribute(self, node):
		name = self.visit(node.value)
		attr = node.attr
		return '%s.%s' % (name, attr)

	def visit_Print(self, node):
		args = [self.visit(e) for e in node.values]
		s = 'console.log(%s);' % ', '.join(args)
		return s

	def visit_keyword(self, node):
		if isinstance(node.arg, basestring):
			return node.arg, self.visit(node.value)
		return self.visit(node.arg), self.visit(node.value)

	def _visit_call_helper_instanceof(self, node):
		args = map(self.visit, node.args)
		if len(args) == 2:
			return '%s instanceof %s' %tuple(args)
		else:
			raise SyntaxError( args )

	def visit_Call(self, node):
		name = self.visit(node.func)
		if name == 'instanceof':  ## this gets used by "with javascript:" blocks to test if an instance is a JavaScript type
			return self._visit_call_helper_instanceof( node )

		elif name == 'new':
		    args = map(self.visit, node.args)
		    if len(args) == 1:
		        return ' new %s' %args[0]
		    else:
		        raise SyntaxError( args )

		elif name == 'JSObject':
			if node.keywords:
				kwargs = map(self.visit, node.keywords)
				f = lambda x: '"%s": %s' % (x[0], x[1])
				out = ', '.join(map(f, kwargs))
				return '{%s}' % out
			else:
				return 'Object()'

		elif name == 'var':
			args = [ self.visit(a) for a in node.args ]
			if self._function_stack:
				fnode = self._function_stack[-1]
				rem = []
				for arg in args:
					if arg in fnode._local_vars:
						rem.append( arg )
					else:
						fnode._local_vars.add( arg )
				for arg in rem:
					args.remove( arg )

			if args:
				out = ', '.join(args)
				return 'var %s' % out
			else:
				return ''

		elif name == 'JSArray':
			if node.args:
				args = map(self.visit, node.args)
				out = ', '.join(args)
				return '__create_array__(%s)' % out
			else:
				return '[]'

		elif name == 'JS':
			s = node.args[0].s.replace('\n', '\\n').replace('\0', '\\0')  ## AttributeError: 'BinOp' object has no attribute 's' - this is caused by bad quotes
			if s.strip().startswith('#'): s = '/*%s*/'%s
			if '"' in s or "'" in s:  ## can not trust direct-replace hacks
				pass
			else:
				if ' or ' in s:
					s = s.replace(' or ', ' || ')
				if ' not ' in s:
					s = s.replace(' not ', ' ! ')
				if ' and ' in s:
					s = s.replace(' and ', ' && ')
			return s

		elif name == 'dart_import':
			if len(node.args) == 1:
				return 'import "%s";' %node.args[0].s
			elif len(node.args) == 2:
				return 'import "%s" as %s;' %(node.args[0].s, node.args[1].s)
			else:
				raise SyntaxError


		else:
			if node.args:
				args = [self.visit(e) for e in node.args]
				args = ', '.join([e for e in args if e])
			else:
				args = ''
			return '%s(%s)' % (name, args)

	def visit_While(self, node):
		body = [ 'while(%s) {' %self.visit(node.test)]
		self.push()
		for line in list( map(self.visit, node.body) ):
			body.append( self.indent()+line )
		self.pull()
		body.append( self.indent() + '}' )
		return '\n'.join( body )

	def visit_Str(self, node):
		s = node.s.replace('\n', '\\n')
		if '"' in s:
			return "'%s'" % s
		return '"%s"' % s

	def visit_BinOp(self, node):
		left = self.visit(node.left)
		op = self.visit(node.op)
		right = self.visit(node.right)
		return '(%s %s %s)' % (left, op, right)

	def visit_Mult(self, node):
		return '*'

	def visit_Add(self, node):
		return '+'

	def visit_Sub(self, node):
		return '-'

	def visit_Div(self, node):
		return '/'

	def visit_Mod(self, node):
		return '%'

	def visit_Lt(self, node):
		return '<'

	def visit_Gt(self, node):
		return '>'

	def visit_GtE(self, node):
		return '>='

	def visit_LtE(self, node):
		return '<='

	def visit_LShift(self, node):
		return '<<'
	def visit_RShift(self, node):
		return '>>'
	def visit_BitXor(self, node):
		return '^'
	def visit_BitOr(self, node):
		return '|'
	def visit_BitAnd(self, node):
		return '&'


	def visit_Assign(self, node):
		# XXX: I'm not sure why it is a list since, mutiple targets are inside a tuple
		target = node.targets[0]
		if isinstance(target, Tuple):
			raise NotImplementedError
		else:
			target = self.visit(target)
			value = self.visit(node.value)
			code = '%s = %s;' % (target, value)
			return code

	def visit_Expr(self, node):
		# XXX: this is UGLY
		s = self.visit(node.value)
		if not s.endswith(';'):
			s += ';'
		return s

	def visit_Return(self, node):
		if isinstance(node.value, Tuple):
			return 'return [%s];' % ', '.join(map(self.visit, node.value.elts))
		if node.value:
			return 'return %s;' % self.visit(node.value)
		return 'return undefined;'

	def visit_Pass(self, node):
		return '/*pass*/'

	def visit_Eq(self, node):
		return '=='

	def visit_NotEq(self, node):
		return '!='

	def visit_Num(self, node):
		return str(node.n)

	def visit_Is(self, node):
		return '==='

	def visit_Compare(self, node):
		comp = [ '(']
		comp.append( self.visit(node.left) )
		comp.append( ')' )

		for i in range( len(node.ops) ):
			comp.append( self.visit(node.ops[i]) )

			if isinstance(node.comparators[i], ast.BinOp):
				comp.append('(')
				comp.append( self.visit(node.comparators[i]) )
				comp.append(')')
			else:
				comp.append( self.visit(node.comparators[i]) )

		return ' '.join( comp )

	def visit_Not(self, node):
		return '!'

	def visit_IsNot(self, node):
		return '!=='

	def visit_UnaryOp(self, node):
		#return self.visit(node.op) + self.visit(node.operand)
		return '%s (%s)' %(self.visit(node.op),self.visit(node.operand))

	def visit_USub(self, node):
		return '-'
		
	def visit_And(self, node):
		return ' && '

	def visit_Or(self, node):
		return ' || '

	def visit_BoolOp(self, node):
		op = self.visit(node.op)
		return op.join( [self.visit(v) for v in node.values] )

	def visit_If(self, node):
		out = []
		out.append( 'if (%s) {' %self.visit(node.test) )
		self.push()

		for line in list(map(self.visit, node.body)):
			out.append( self.indent() + line )

		orelse = []
		for line in list(map(self.visit, node.orelse)):
			orelse.append( self.indent() + line )

		self.pull()

		if orelse:
			out.append( self.indent() + '} else {')
			out.extend( orelse )
		out.append( self.indent() + '}' )

		return '\n'.join( out )


	def visit_Dict(self, node):
		a = []
		for i in range( len(node.keys) ):
			k = self.visit( node.keys[ i ] )
			v = self.visit( node.values[i] )
			a.append( '%s:%s'%(k,v) )
		b = ','.join( a )
		return '{ %s }' %b


	def _visit_for_prep_iter_helper(self, node, out, iter_name):
		## support "for key in JSObject" ##
		#out.append( self.indent() + 'if (! (iter instanceof Array) ) { iter = Object.keys(iter) }' )
		## new style - Object.keys only works for normal JS-objects, not ones created with `Object.create(null)`
		out.append(
			self.indent() + 'if (! (%s instanceof Array) ) { %s = __object_keys__(%s) }' %(iter_name, iter_name, iter_name)
		)


	_iter_id = 0
	def visit_For(self, node):
		'''
		for loops inside a `with javascript:` block will produce this faster for loop.

		note that the rules are python-style, even though we are inside a `with javascript:` block:
			. an Array is like a list, `for x in Array` gives you the value (not the index as you would get in pure javascript)
			. an Object is like a dict, `for v in Object` gives you the key (not the value as you would get in pure javascript)

		if your are trying to opitmize looping over a PythonJS list, you can do this:
			for v in mylist[...]:
				print v
		above works because [...] returns the internal Array of mylist

		'''
		self._iter_id += 1
		iname = '__iter%s' %self._iter_id
		index = '__idx%s' %self._iter_id

		target = node.target.id
		iter = self.visit(node.iter) # iter is the python iterator

		out = []
		out.append( self.indent() + 'var %s = %s;' % (iname, iter) )
		#out.append( self.indent() + 'var %s = 0;' % index )

		self._visit_for_prep_iter_helper(node, out, iname)

		out.append( self.indent() + 'for (var %s=0; %s < %s.length; %s++) {' % (index, index, iname, index) )
		self.push()

		body = []
		# backup iterator and affect value of the next element to the target
		#pre = 'var backup = %s; %s = iter[%s];' % (target, target, target)
		body.append( self.indent() + 'var %s = %s[ %s ];' %(target, iname, index) )

		for line in list(map(self.visit, node.body)):
			body.append( self.indent() + line )

		# replace the replace target with the javascript iterator
		#post = '%s = backup;' % target
		#body.append( self.indent() + post )

		self.pull()
		out.extend( body )
		out.append( self.indent() + '}' )

		return '\n'.join( out )

	def visit_Continue(self, node):
		return 'continue'

	def visit_Break(self, node):
		return 'break;'

def main(script):
	tree = ast.parse( script )
	return JSGenerator().visit(tree)


def command():
	scripts = []
	if len(sys.argv) > 1:
		for arg in sys.argv[1:]:
			if arg.endswith('.py'):
				scripts.append( arg )

	if len(scripts):
		a = []
		for script in scripts:
			a.append( open(script, 'rb').read() )
		data = '\n'.join( a )
	else:
		data = sys.stdin.read()

	js = main( data )
	print( js )


if __name__ == '__main__':
	command()
