// Audit-only in-memory transform; candidate product and test files stay untouched.
export default {
  test: { environment: 'node', include: ['src/**/*.test.ts', 'src/**/*.test.tsx'] },
  plugins: [{
    name: 'audit-collapse-seller-boundary', enforce: 'pre',
    transform(code, id) {
      if (process.env.WMS_AUDIT_MUTATION !== 'collapse_seller' || !id.endsWith('/fbsSupplyAssembly.ts')) return null
      const needle = '    order.seller.id,'
      if (code.split(needle).length !== 2) throw new Error('Unexpected product source; refuse mutation')
      console.log('WMS_AUDIT_PRODUCT_MUTATION=collapse_seller APPLIED')
      return { code: code.replace(needle, '    "all-sellers",'), map: null }
    },
  }],
}
